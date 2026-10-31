#!/usr/bin/env python3
"""Serves the Qwenputer Doom live view and takes the controls.

Static files (index.html, latest.png) come from this directory; two POST
endpoints drive the game through control.bin, an 8-byte file the fast
runner mmaps:

  bytes 0..3  key mask, little-endian (bit per key: 0 up, 1 down,
              2 left, 3 right, 4 fire, 5 use, 6 enter, 7 escape)
  byte 4      mode: 0 = demo script drives, 1 = manual (the runner
              clears the guest's demo flag and pokes the mask into its
              key-state cell at frame boundaries)

  POST /api/keys  {"mask": N}
  POST /api/mode  {"mode": "demo" | "manual"}   (demo also zeroes the mask)
  GET  /api/status -> {"mode": ..., "mask": N}
"""
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTROL = HERE / "control.bin"
PORT = 8950


def write_control(mask=None, mode=None):
    fd = os.open(CONTROL, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        buf = bytearray(os.pread(fd, 8, 0).ljust(8, b"\0"))
        if mask is not None:
            buf[0:4] = (mask & 0xFF).to_bytes(4, "little")
        if mode is not None:
            buf[4] = mode
        os.pwrite(fd, bytes(buf), 0)
    finally:
        os.close(fd)


def read_control():
    try:
        buf = os.pread(os.open(CONTROL, os.O_RDONLY), 8, 0).ljust(8, b"\0")
    except OSError:
        buf = bytes(8)
    return {"mode": "manual" if buf[4] else "demo", "mask": buf[0]}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, obj, code=200):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/api/status":
            self._json(read_control())
        else:
            super().do_GET()

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            data = {}
        if self.path == "/api/keys":
            write_control(mask=int(data.get("mask", 0)))
            self._json({"ok": True})
        elif self.path == "/api/mode":
            mode = 1 if data.get("mode") == "manual" else 0
            write_control(mode=mode, mask=0 if mode == 0 else None)
            self._json({"ok": True, "mode": "manual" if mode else "demo"})
        else:
            self._json({"ok": False, "error": "unknown endpoint"}, 404)


if __name__ == "__main__":
    write_control(mask=0, mode=0)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
