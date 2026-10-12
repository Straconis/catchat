# Cat Chat relay

Python entry file: `relay.py`. Dependency: Pillow (`python -m pip install Pillow`). No GUI or cat library is needed on the server.

For Bot-Hosting, select Python, upload relay.py and requirements.txt, and set these environment variables in the hosting configuration:

```
HOST=0.0.0.0
PORT=<your assigned port>
CAT_CHAT_TOKEN=<a random token at least 32 characters long>
CAT_CHAT_DB=cat-chat.db
```

Generate a token locally with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Put it in the desktop client's **Relay access token** field. The shared message secret is separate and stays on the devices.

Use an HTTPS endpoint that proxies to the assigned relay port; do not send the relay token over public plain HTTP. The host's HTTPS/proxy setup must be configured separately. The standard-library HTTP server is intended for a small controlled pilot behind that proxy, not an unrestricted public service.

The server stores SQLite data on disk. Keep that file on persistent storage. `/health` is an unauthenticated health check. Message endpoints require the configured bearer token. The pilot uses one access token for trusted participants, not individual accounts; everyone with the token can access known rooms. Use hard-to-guess room names. Encryption still depends on the separately shared message secret.

Limits: 2 MiB JSON uploads, 60 upload attempts/minute across the relay, 1,000 queued images, 256 MiB stored base64 image data. Images expire after 24 hours; cleanup occurs on message requests. Limits return clear errors rather than silently dropping uploads. The SQLite file may retain allocated space after expiry.

Local testing works without a token while bound to localhost: `python relay.py`. Public interface binding requires a token with at least 32 characters. Android client and per-user accounts are not included yet.
