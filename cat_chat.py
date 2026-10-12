"""Cat Chat Windows prototype. Run with Python, or package with PyInstaller."""
import base64
import hashlib
import io
import json
import os
import queue
import random
import struct
import sys
import threading
import tkinter as tk
import urllib.request
import uuid
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
MAGIC = b'CAT1'

def encode(image, text, password):
    if not password:
        raise ValueError('Enter a shared secret first.')
    salt, nonce = os.urandom(16), os.urandom(12)
    key = Scrypt(salt=salt, length=32, n=16384, r=8, p=1).derive(password.encode())
    payload = salt + nonce + AESGCM(key).encrypt(nonce, text.encode('utf-8'), MAGIC)
    data = MAGIC + struct.pack('>I', len(payload)) + payload
    rgb = image.convert('RGB')
    pixels = bytearray(rgb.tobytes())
    if len(data) * 8 > len(pixels):
        raise ValueError('This image is too small for the message. Choose a larger cat.')
    for i, byte in enumerate(data):
        for bit in range(8):
            index = i * 8 + bit
            pixels[index] = (pixels[index] & 254) | ((byte >> (7-bit)) & 1)
    result = Image.frombytes('RGB', rgb.size, bytes(pixels))
    output = io.BytesIO()
    result.save(output, format='PNG')
    return output.getvalue()

def decode(png, password):
    image = Image.open(io.BytesIO(png)).convert('RGB')
    pixels = image.tobytes()
    def read(count):
        if count * 8 > len(pixels):
            raise ValueError('Incomplete Cat Chat image.')
        return bytes(sum((pixels[i*8+b] & 1) << (7-b) for b in range(8)) for i in range(count))
    header = read(8)
    if header[:4] != MAGIC:
        raise ValueError('This image does not contain a Cat Chat message.')
    length = struct.unpack('>I', header[4:])[0]
    if length < 44:
        raise ValueError('Invalid Cat Chat payload.')
    payload = read(8 + length)[8:]
    key = Scrypt(salt=payload[:16], length=32, n=16384, r=8, p=1).derive(password.encode())
    try:
        return AESGCM(key).decrypt(payload[16:28], payload[28:], MAGIC).decode('utf-8'), image
    except Exception as error:
        raise ValueError('Wrong shared secret, or the image was changed.') from error

class Chat:
    def __init__(self, root):
        self.root, self.events = root, queue.Queue()
        self.client = uuid.uuid4().hex
        self.cursor = 0
        self.connected = False
        self.last_png = None
        self.photos = []
        self.cats = sorted((ROOT / 'real-cats').glob('*.png'))
        root.title('Cat Chat — secret messages, excellent cats')
        root.geometry('1050x820')
        root.minsize(800, 650)
        logo_path = ROOT / 'assets' / 'catchat-logo.png'
        if logo_path.exists():
            with Image.open(logo_path) as logo:
                self.window_icon = ImageTk.PhotoImage(logo.resize((64, 64), Image.Resampling.LANCZOS))
                self.header_logo = ImageTk.PhotoImage(logo.resize((76, 76), Image.Resampling.LANCZOS))
            root.iconphoto(True, self.window_icon)
        style = self.style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background='#f4f5fa')
        style.configure('TLabel', background='#f4f5fa', foreground='#273249', font=('Segoe UI', 10))
        style.configure('TButton', font=('Segoe UI', 10), padding=7)
        top = ttk.Frame(root, padding=16); top.pack(fill='x')
        if hasattr(self, 'header_logo'):
            ttk.Label(top, image=self.header_logo).pack(side='left', padx=(0, 12))
        self.theme_button = ttk.Button(top, text='Light mode', command=self.toggle_theme)
        self.theme_button.pack(side='right')
        ttk.Label(top, text='CAT CHAT', font=('Segoe UI', 23, 'bold')).pack(anchor='w')
        ttk.Label(top, text='Tiny secrets. Big cat energy.').pack(anchor='w')
        connection = ttk.Frame(root, padding=(16, 0)); connection.pack(fill='x')
        self.url = tk.StringVar(value='http://127.0.0.1:8787')
        self.room = tk.StringVar(value='our-cats')
        self.secret = tk.StringVar()
        for label, variable, width, show in [('Relay URL', self.url, 30, ''), ('Room', self.room, 15, ''), ('Shared secret', self.secret, 20, '*')]:
            box = ttk.Frame(connection); box.pack(side='left', padx=(0, 12))
            ttk.Label(box, text=label).pack(anchor='w')
            ttk.Entry(box, textvariable=variable, width=width, show=show).pack()
        self.connect_button = ttk.Button(connection, text='Connect', command=self.connect); self.connect_button.pack(side='left', pady=16)
        access = ttk.Frame(root, padding=(16, 0)); access.pack(fill='x')
        ttk.Label(access, text='Relay access token (if required)').pack(side='left', padx=(0, 8))
        self.token = tk.StringVar(value=os.environ.get('CAT_CHAT_TOKEN', ''))
        ttk.Entry(access, textvariable=self.token, show='*', width=45).pack(side='left')
        self.status = tk.StringVar(value='Offline • Preview works without a server')
        ttk.Label(root, textvariable=self.status, padding=(16, 8)).pack(anchor='w')
        outer = ttk.Frame(root, padding=(16, 0)); outer.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(outer, background='#f4f5fa', highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y'); self.canvas.pack(side='left', fill='both', expand=True)
        self.history = ttk.Frame(self.canvas)
        window = self.canvas.create_window((0, 0), window=self.history, anchor='nw')
        self.history.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(window, width=e.width))
        self.canvas.bind_all('<MouseWheel>', lambda e: self.canvas.yview_scroll(-int(e.delta / 120), 'units'))
        self.canvas.bind_all('<Button-4>', lambda e: self.canvas.yview_scroll(-1, 'units'))
        self.canvas.bind_all('<Button-5>', lambda e: self.canvas.yview_scroll(1, 'units'))
        compose = ttk.Frame(root, padding=16); compose.pack(fill='x')
        self.cat_name = tk.StringVar()
        ttk.Label(compose, textvariable=self.cat_name).pack(anchor='w')
        buttons = ttk.Frame(compose); buttons.pack(fill='x', pady=6)
        ttk.Button(buttons, text='Choose image / library…', command=self.choose).pack(side='left')
        ttk.Button(buttons, text='Random Cat', command=self.random_cat).pack(side='left', padx=6)
        ttk.Button(buttons, text='Open received PNG…', command=self.open_png).pack(side='left')
        ttk.Button(buttons, text='Save last PNG…', command=self.save_png).pack(side='left', padx=6)
        self.composer = tk.Text(compose, height=3, font=('Segoe UI', 11), wrap='word')
        self.composer.pack(fill='x', pady=6)
        ttk.Button(compose, text='Send Cat' , command=lambda: self.send(False)).pack(side='right')
        ttk.Button(compose, text='Local preview', command=lambda: self.send(True)).pack(side='right', padx=6)
        self.random_cat()
        self.dark = True
        self.apply_theme()
        root.after(100, self.drain)

    def toggle_theme(self):
        self.dark = not self.dark
        self.apply_theme()

    def apply_theme(self):
        bg, field, fg, edge, accent = ('#171b24', '#242b38', '#e8edf5', '#39465a', '#80b9ff') if self.dark else ('#f4f5fa', '#ffffff', '#273249', '#c7cfdd', '#225fa8')
        self.root.configure(background=bg)
        for name in ['TFrame', 'TLabel', 'TLabelframe']:
            self.style.configure(name, background=bg, foreground=fg)
        self.style.configure('TLabelframe', bordercolor=edge)
        self.style.configure('TLabelframe.Label', background=bg, foreground=accent)
        self.style.configure('TEntry', fieldbackground=field, foreground=fg, insertcolor=fg, bordercolor=edge)
        self.style.map('TEntry', fieldbackground=[('disabled', bg)], foreground=[('disabled', fg)])
        self.style.configure('TButton', background=field, foreground=fg, bordercolor=edge)
        self.style.map('TButton', background=[('active', edge), ('pressed', edge)], foreground=[('active', fg), ('pressed', fg)])
        self.style.configure('Vertical.TScrollbar', background=field, troughcolor=bg, bordercolor=bg, arrowcolor=fg)
        self.canvas.configure(background=bg)
        self.composer.configure(background=field, foreground=fg, insertbackground=fg, selectbackground='#3263a1', selectforeground='#ffffff', highlightbackground=edge, highlightcolor=accent, relief='flat', padx=10, pady=8)
        self.theme_button.configure(text='Light mode' if self.dark else 'Dark mode')
        if sys.platform == 'win32':
            try:
                import ctypes
                self.root.update_idletasks()
                hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
                value = ctypes.c_int(int(self.dark))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
            except Exception:
                pass

    def random_cat(self):
        if not self.cats:
            self.selected = None
            self.cat_name.set('Choose your own image, or download the bundled library with tools/download_cats.py')
            return
        self.selected = random.choice(self.cats)
        self.cat_name.set('Selected: ' + self.selected.name)

    def choose(self):
        path = filedialog.askopenfilename(initialdir=str(ROOT / 'real-cats'), filetypes=[('Images', '*.png *.jpg *.jpeg *.webp *.bmp')])
        if path:
            self.selected = Path(path); self.cat_name.set('Selected: ' + self.selected.name)

    def connect(self):
        if self.connected:
            self.connected = False
            self.connect_button.configure(text='Connect')
            self.status.set('Disconnected')
            return
        if not self.secret.get():
            messagebox.showerror('Shared secret needed', 'Both people must enter the same shared secret.'); return
        self.endpoint = self.url.get().rstrip('/')
        self.room_id = hashlib.sha256(self.room.get().encode()).hexdigest()
        self.password = self.secret.get()
        self.room_label = self.room.get()
        self.access_token = self.token.get()
        self.connected = True
        self.connect_button.configure(text='Disconnect')
        self.status.set('Connecting…')
        threading.Thread(target=self.poll, daemon=True).start()

    def request(self, data=None):
        headers = {'Content-Type': 'application/json'}
        if self.access_token:
            headers['Authorization'] = 'Bearer ' + self.access_token
        req = urllib.request.Request(self.endpoint + '/messages?room=' + self.room_id + '&after=' + str(self.cursor), data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)

    def poll(self):
        import time
        while self.connected:
            try:
                response = self.request()
                self.events.put(('status', 'Connected • ' + self.room_label))
                for item in response['messages']:
                    if item['sender'] != self.client:
                        png = base64.b64decode(item['png'])
                        try:
                            text, image = decode(png, self.password)
                            self.events.put(('message', text, image, 'Received', png))
                        except Exception as error:
                            self.events.put(('status', 'Cannot read received cat: ' + str(error)))
                    self.cursor = max(self.cursor, item['id'])
            except Exception as error:
                self.events.put(('status', 'Relay unavailable • ' + str(error)))
            time.sleep(2)

    def send(self, preview):
        text = self.composer.get('1.0', 'end').strip()
        if not text: return
        if self.selected is None:
            messagebox.showinfo('Choose a cat', 'Select an image first using Choose image / library.'); return
        if not preview and not self.connected:
            messagebox.showinfo('Connect first', 'Connect to a relay, or use Local preview.'); return
        password = self.password if self.connected else self.secret.get()
        try:
            with Image.open(self.selected) as im:
                png = encode(im, text, password)
            decoded, image = decode(png, password)
        except Exception as error:
            messagebox.showerror('Could not encode cat', str(error)); return
        if preview:
            self.add_message(decoded, image, 'Local preview', png)
            return
        def upload():
            try:
                self.request(json.dumps({'sender': self.client, 'png': base64.b64encode(png).decode()}).encode())
                self.events.put(('message', decoded, image, 'Sent', png))
                self.events.put(('clear', text))
            except Exception as error:
                self.events.put(('status', 'Send failed • ' + str(error)))
        threading.Thread(target=upload, daemon=True).start()

    def add_message(self, text, image, label, png):
        self.last_png = png
        row = ttk.Frame(self.history, padding=10); row.pack(fill='x', pady=6)
        ttk.Label(row, text=label, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        panels = ttk.Frame(row); panels.pack(fill='x', pady=6)
        left = ttk.LabelFrame(panels, text='Decoded message', padding=12); left.pack(side='left', fill='both', expand=True, padx=(0, 10))
        ttk.Label(left, text=text, wraplength=400, justify='left', font=('Segoe UI', 12)).pack(anchor='nw')
        right = ttk.LabelFrame(panels, text='Lolcat carrier', padding=8); right.pack(side='right')
        thumbnail = image.copy(); thumbnail.thumbnail((330, 250))
        photo = ImageTk.PhotoImage(thumbnail); self.photos.append(photo)
        ttk.Label(right, image=photo).pack()
        self.root.after(50, lambda: self.canvas.yview_moveto(1))

    def open_png(self):
        path = filedialog.askopenfilename(filetypes=[('Cat Chat PNG', '*.png')])
        if not path: return
        try:
            png = Path(path).read_bytes()
            text, image = decode(png, self.secret.get())
            self.add_message(text, image, 'Imported', png)
        except Exception as error:
            messagebox.showerror('Could not read cat', str(error))

    def save_png(self):
        if not self.last_png: return
        path = filedialog.asksaveasfilename(defaultextension='.png', initialfile='secret-cat.png', filetypes=[('PNG', '*.png')])
        if path: Path(path).write_bytes(self.last_png)

    def drain(self):
        while not self.events.empty():
            event = self.events.get()
            if event[0] == 'status': self.status.set(event[1])
            elif event[0] == 'message': self.add_message(*event[1:])
            elif event[0] == 'clear' and self.composer.get('1.0', 'end').strip() == event[1]: self.composer.delete('1.0', 'end')
        self.root.after(100, self.drain)

if __name__ == '__main__':
    Chat(tk.Tk()).root.mainloop()
