"""Development relay: python relay.py. Put behind HTTPS before internet use."""
import base64
import io
import json
import os
import sqlite3
import time
import secrets
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from PIL import Image

DB = os.environ.get('CAT_CHAT_DB', 'cat-chat.db')
LIMIT = 2 * 1024 * 1024
TOKEN = os.environ.get('CAT_CHAT_TOKEN', '')
rate_lock = threading.Lock()
uploads = deque()
with sqlite3.connect(DB) as db:
    db.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, room TEXT, sender TEXT, png TEXT, created REAL)')

class Handler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def dispatch(self, upload=False):
        try:
            self.connection.settimeout(15)
            parsed = urlparse(self.path)
            if parsed.path == '/health' and not upload:
                self.reply(200, {'ok': True}); return
            if parsed.path != '/messages': self.reply(404, {'error': 'Not found'}); return
            if TOKEN and not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + TOKEN):
                self.reply(401, {'error': 'Relay access token required'}); return
            query = parse_qs(parsed.query)
            room = query.get('room', [''])[0]
            if len(room) != 64 or any(c not in '0123456789abcdef' for c in room):
                raise ValueError('Invalid room')
            with sqlite3.connect(DB, timeout=10) as db:
                db.execute('DELETE FROM messages WHERE created < ?', (time.time() - 86400,))
                if upload:
                    with rate_lock:
                        now = time.monotonic()
                        while uploads and uploads[0] < now - 60: uploads.popleft()
                        if len(uploads) >= 60:
                            self.reply(429, {'error': 'Relay upload limit reached. Try again shortly.'}); return
                        uploads.append(now)
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= LIMIT:
                        self.reply(413, {'error': 'Upload too large'}); return
                    data = json.loads(self.rfile.read(length))
                    png = base64.b64decode(data['png'], validate=True)
                    if not png.startswith(b'\x89PNG\r\n\x1a\n'): raise ValueError('PNG required')
                    with Image.open(io.BytesIO(png)) as im: im.verify()
                    sender = data['sender']
                    if not isinstance(sender, str) or len(sender) > 64: raise ValueError('Invalid sender')
                    count, stored = db.execute('SELECT COUNT(*), COALESCE(SUM(LENGTH(png)),0) FROM messages').fetchone()
                    if count >= 1000 or stored + len(data['png']) > 256 * 1024 * 1024:
                        self.reply(503, {'error': 'Relay storage full'}); return
                    db.execute('INSERT INTO messages(room,sender,png,created) VALUES(?,?,?,?)', (room, sender, data['png'], time.time()))
                    self.reply(200, {'ok': True})
                else:
                    after = int(query.get('after', ['0'])[0])
                    rows = db.execute('SELECT id,sender,png FROM messages WHERE room=? AND id>? ORDER BY id LIMIT 20', (room, after)).fetchall()
                    self.reply(200, {'messages': [dict(zip(['id', 'sender', 'png'], row)) for row in rows]})
        except (ValueError, KeyError, OSError, TypeError, sqlite3.Error) as error:
            self.reply(400, {'error': str(error)})

    def do_GET(self): self.dispatch()
    def do_POST(self): self.dispatch(True)

if __name__ == '__main__':
    host = os.environ.get('HOST', '127.0.0.1')
    port = int(os.environ.get('PORT', '8787'))
    if host not in ('127.0.0.1', 'localhost', '::1') and len(TOKEN) < 32:
        raise SystemExit('Set CAT_CHAT_TOKEN to a random token of at least 32 characters before exposing the relay.')
    print(f'Cat Chat development relay on {host}:{port}')
    ThreadingHTTPServer((host, port), Handler).serve_forever()
