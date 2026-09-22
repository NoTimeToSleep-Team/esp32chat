"""LC Bridge daemon: ESP-NOW bridge (USB serial) <-> local chat server.

The M5Stamp S3 bridge is connected to the RPi over USB and appears as a
serial port. This daemon reads framed JSON requests from the bridge, executes
them as HTTP requests against the local server and writes framed responses
back to the bridge (which forwards them to the device over ESP-NOW).

Uses only the Python standard library (termios) - no pyserial required.

Frame: [0xAA][type:1][len:2 LE][mac:6][payload:len]
  type 0x01 request (bridge -> daemon), 0x02 response (daemon -> bridge),
  0x03 hello (bridge -> daemon)

Request payload:  {"id": 12, "m": "GET", "p": "/chat/api/chats?...", "b": "..."}
Response payload: {"id": 12, "s": 200, "b": "..."}

Env:
    LC_BRIDGE_PORT  serial port (auto-detected /dev/ttyACM* if unset)
    LC_BRIDGE_BASE  server base URL (default http://127.0.0.1:18080)
"""

from __future__ import annotations

import glob
import json
import os
import select
import sys
import termios
import time
import urllib.error
import urllib.request

USB_MAGIC = 0xAA
BASE = os.environ.get("LC_BRIDGE_BASE", "http://127.0.0.1:18080")
PORT = os.environ.get("LC_BRIDGE_PORT", "")
HTTP_TIMEOUT = float(os.environ.get("LC_BRIDGE_HTTP_TIMEOUT", "15"))


def find_port() -> str | None:
    if PORT:
        return PORT
    for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*"):
        devices = sorted(glob.glob(pattern))
        if devices:
            return devices[0]
    return None


def open_port(dev: str) -> int:
    fd = os.open(dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = attrs
    iflag = 0
    oflag = 0
    lflag = 0
    cflag = termios.CS8 | termios.CREAD | termios.CLOCAL
    ispeed = termios.B115200
    ospeed = termios.B115200
    cc = list(cc)
    cc[termios.VMIN] = 0
    cc[termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, ispeed, ospeed, cc])
    return fd


def execute(payload: bytes) -> dict:
    try:
        req = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return {"id": 0, "s": 0, "b": json.dumps({"error": f"bad request: {exc}"})}

    rid = int(req.get("id", 0))
    method = str(req.get("m", "GET")).upper()
    path = str(req.get("p", "/"))
    body = req.get("b", "")
    data = body.encode("utf-8") if body else None

    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as resp:
            text = resp.read().decode("utf-8", "replace")
            return {"id": rid, "s": resp.status, "b": text}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        return {"id": rid, "s": exc.code, "b": text}
    except Exception as exc:  # noqa: BLE001
        return {"id": rid, "s": 0, "b": json.dumps({"error": str(exc)})}


def send_frame(fd: int, ftype: int, mac: bytes, payload: bytes) -> None:
    header = bytes(
        [USB_MAGIC, ftype, len(payload) & 0xFF, (len(payload) >> 8) & 0xFF]
    ) + mac
    os.write(fd, header + payload)


def run_session(fd: int) -> None:
    buf = bytearray()
    while True:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if ready:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                return
            if chunk:
                buf.extend(chunk)

        # Log text output from the bridge (diagnostics); frames start with 0xAA.
        if buf and buf[0] != USB_MAGIC:
            text = bytes(buf).decode("utf-8", "ignore")
            if "\n" in text:
                parts = text.split("\n")
                for line in parts[:-1]:
                    if line.strip():
                        print(f"bridge log: {line.strip()}", flush=True)
                buf = bytearray(parts[-1].encode("utf-8"))

        while len(buf) >= 10:
            if buf[0] != USB_MAGIC:
                idx = buf.find(bytes([USB_MAGIC]))
                if idx < 0:
                    buf.clear()
                    break
                del buf[:idx]
                continue
            length = buf[2] | (buf[3] << 8)
            if len(buf) < 10 + length:
                break
            ftype = buf[1]
            mac = bytes(buf[4:10])
            payload = bytes(buf[10 : 10 + length])
            del buf[: 10 + length]

            if ftype == 0x01:
                result = execute(payload)
                send_frame(fd, 0x02, mac, json.dumps(result).encode("utf-8"))
                print(
                    f"request mac={mac.hex(':')} status={result['s']} "
                    f"req={len(payload)}B resp={len(result['b'])}B",
                    flush=True,
                )
            elif ftype == 0x03:
                print(f"bridge hello mac={mac.hex(':')}", flush=True)


def main() -> None:
    while True:
        port = find_port()
        if not port:
            print("bridge port not found, retry in 3s", flush=True)
            time.sleep(3)
            continue
        try:
            fd = open_port(port)
        except Exception as exc:  # noqa: BLE001
            print(f"open {port} failed: {exc}, retry in 3s", flush=True)
            time.sleep(3)
            continue

        print(f"bridge daemon: port={port} base={BASE}", flush=True)
        try:
            run_session(fd)
        except Exception as exc:  # noqa: BLE001
            print(f"serial session error: {exc}", flush=True)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass
        time.sleep(2)


if __name__ == "__main__":
    main()
