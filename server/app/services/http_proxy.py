#!/usr/bin/env python3
"""
Transparent HTTP/HTTPS proxy with captive portal.
- Port 3128: all TCP traffic intercepted via iptables REDIRECT (ports 80 + 443)
- Checks internet_access per client IP via DB
- Internet OFF: returns captive portal page (HTTP) or drops connection (HTTPS)
- Internet ON: forwards to real destination, injects server banner (HTTP only)
"""

import socket
import struct
import threading
import select
import sqlite3
import json
import time
import re
import os

PROXY_PORT = 3128
SERVER_URL = os.environ.get("LC_SERVER_URL", "http://192.168.4.1:18080")
DB_PATH = os.environ.get(
    "LC_DB_PATH",
    "/opt/local-chat-server/data/sqlite/local_chat.db",
)

BANNER_HTML = """
<div id="lc-banner" style="
  position:fixed;top:0;left:0;right:0;z-index:99999;
  background:#0d1117;color:#fff;padding:8px 16px;
  font:14px monospace;text-align:center;
  border-bottom:2px solid #238636;display:flex;justify-content:center;gap:16px
">
  <a href="SERVER_URL" style="color:#58a6ff;text-decoration:none;font-weight:bold">LC Chat</a>
  <a href="SERVER_URL/blog" style="color:#58a6ff;text-decoration:none">Blog</a>
  <a href="SERVER_URL/support" style="color:#58a6ff;text-decoration:none">Support</a>
</div>
""".replace("SERVER_URL", SERVER_URL)

CAPTIVE_HTML = """HTTP/1.1 200 OK\r
Content-Type: text/html; charset=utf-8\r
Cache-Control: no-store, no-cache, must-revalidate\r
Pragma: no-cache\r
Expires: 0\r
Connection: close\r
\r
<!DOCTYPE html><html><head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no'>
<meta name='theme-color' content='#0d1117'>
<meta http-equiv='Cache-Control' content='no-cache'>
<title>LC Chat</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#e6edf3;font:14px -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;padding:20px}
.card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:24px;width:100%;max-width:380px}
h2{color:#58a6ff;margin-bottom:4px;font-size:20px}
.sub{color:#8b949e;margin-bottom:20px;font-size:13px}
label{display:block;color:#8b949e;margin-bottom:4px;font-size:12px}
input{width:100%;background:#0d1117;color:#e6edf3;border:1px solid #30363d;padding:10px 12px;border-radius:6px;font:14px monospace;margin-bottom:12px}
input:focus{outline:none;border-color:#58a6ff}
button{width:100%;background:#238636;color:#fff;border:none;padding:10px;border-radius:6px;font:14px monospace;font-weight:bold;cursor:pointer}
button:active{opacity:0.8}
.error{color:#f85149;font-size:12px;margin-bottom:8px;display:none}
.guest-btn{background:#30363d;margin-top:8px}
.open-link{margin-top:16px;text-align:center;font-size:12px;color:#8b949e}
.open-link a{color:#58a6ff}
</style>
</head><body>
<div class='card'>
<h2>LC Chat</h2>
<div class='sub'>Sign in to access internet</div>
<div class='error' id='err'></div>
<form method='POST' action='/captive-login'>
<input name='login' type='text' placeholder='Login' autocomplete='username' required>
<input name='password' type='password' placeholder='Password' autocomplete='current-password' required>
<button type='submit'>Sign In</button>
</form>
<form method='POST' action='/captive-guest'>
<button type='submit' class='guest-btn'>Continue as guest</button>
</form>
<div class='open-link'>Or open <a href='SERVER_URL'>SERVER_URL</a> in browser</div>
</div>
</body></html>""".replace("SERVER_URL", SERVER_URL)

HTTP_METHODS = {b"GET", b"POST", b"HEAD", b"PUT", b"DELETE", b"OPTIONS", b"CONNECT", b"TRACE", b"PATCH"}
SO_ORIGINAL_DST = 80  # Linux netfilter: SOL_IP / SO_ORIGINAL_DST

def get_original_dst(sock) -> tuple[str, int] | None:
    """Get original destination (ip, port) after iptables REDIRECT."""
    try:
        raw = sock.getsockopt(socket.SOL_IP, SO_ORIGINAL_DST, 16)
        port = struct.unpack('!H', raw[2:4])[0]
        ip = socket.inet_ntoa(raw[4:8])
        return ip, port
    except Exception:
        return None

# Cache IP -> internet_enabled, refreshed every 60s
ip_cache: dict[str, bool] = {}
cache_ts = 0

def get_db():
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

def user_ip_to_id(ip: str) -> int | None:
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT user_id FROM sessions WHERE ip_address = ? "
            "AND revoked_at_ms IS NULL AND expires_at_ms > ? "
            "AND client_kind = 'web' "
            "ORDER BY created_at_ms DESC LIMIT 1",
            (ip, int(time.time() * 1000))
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None

def check_internet(ip: str) -> bool:
    global cache_ts
    now = time.time()
    if now - cache_ts > 2:
        ip_cache.clear()
        cache_ts = now
    if ip in ip_cache:
        return ip_cache[ip]

    user_id = user_ip_to_id(ip)
    if user_id is None:
        # No authenticated web session on this client IP: never grant internet.
        # Per-user internet control must not become a global allow rule.
        ip_cache[ip] = False
        return False

    try:
        conn = get_db()
        row = conn.execute("SELECT enabled FROM internet_access WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        enabled = bool(row[0]) if row else False
    except Exception:
        enabled = False

    ip_cache[ip] = enabled
    return enabled

def handle_client(client_sock, client_addr):
    client_ip = client_addr[0]
    try:
        data = client_sock.recv(8192)
        if not data:
            client_sock.close()
            return

        has_internet = check_internet(client_ip)

        # Detect transparent TLS (ClientHello starts with 0x16 0x03 ...)
        is_tls = (data[0] == 0x16 and len(data) > 2 and data[1] == 0x03)

        if is_tls:
            if not has_internet:
                client_sock.close()
                return
            orig = get_original_dst(client_sock)
            if orig is None:
                client_sock.close()
                return
            host, port = orig
            try:
                remote = socket.create_connection((host, port), timeout=15)
                remote.sendall(data)
                def relay(a, b):
                    while True:
                        try:
                            d = a.recv(65535)
                            if not d: break
                            b.sendall(d)
                        except: break
                    try: a.close()
                    except: pass
                    try: b.close()
                    except: pass
                t1 = threading.Thread(target=relay, args=(client_sock, remote), daemon=True)
                t2 = threading.Thread(target=relay, args=(remote, client_sock), daemon=True)
                t1.start(); t2.start()
                t1.join(timeout=120); t2.join(timeout=120)
            except Exception:
                try: client_sock.close()
                except: pass
            return

        # HTTP handling below
        text = data.decode("utf-8", errors="replace")
        lines = text.split("\r\n")
        if not lines:
            client_sock.close()
            return

        req_line = lines[0]
        parts = req_line.split()
        if len(parts) < 2:
            client_sock.close()
            return

        method = parts[0]
        url = parts[1]

        if not has_internet:
            # 302 redirect to portal - iOS/Android will open system browser
            redirect = (
                "HTTP/1.1 302 Found\r\n"
                "Location: SERVER_URL\r\n"
                "Cache-Control: no-store, no-cache, must-revalidate\r\n"
                "Connection: close\r\n\r\n"
            ).replace("SERVER_URL", SERVER_URL)
            client_sock.sendall(redirect.encode())
            client_sock.close()
            return

        # Internet enabled: forward clean (no banner injection for mobile compat)
        if method == "CONNECT":
            # HTTPS: can't inject banner, just forward
            host_port = url.split(":")
            host = host_port[0]
            port = int(host_port[1]) if len(host_port) > 1 else 443
            try:
                remote = socket.create_connection((host, port), timeout=10)
                client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                def relay(a, b):
                    while True:
                        try:
                            d = a.recv(65535)
                            if not d: break
                            b.sendall(d)
                        except: break
                    try: a.close()
                    except: pass
                    try: b.close()
                    except: pass
                t1 = threading.Thread(target=relay, args=(client_sock, remote), daemon=True)
                t2 = threading.Thread(target=relay, args=(remote, client_sock), daemon=True)
                t1.start(); t2.start()
                t1.join(timeout=60); t2.join(timeout=60)
            except Exception:
                try: client_sock.close()
                except: pass
            return

        # HTTP forward
        host = ""
        port = 80
        path = "/"

        if url.startswith("http://"):
            url = url[7:]
        if "/" in url:
            host, rest = url.split("/", 1)
            path = "/" + rest
        else:
            host = url
        if ":" in host:
            host, p = host.split(":", 1)
            port = int(p)

        # Build forwarded request
        fwd = f"{method} {path} HTTP/1.1\r\n"
        for line in lines[1:]:
            if line.lower().startswith("proxy-"):
                continue
            fwd += line + "\r\n"
        fwd += "Connection: close\r\n\r\n"

        try:
            remote = socket.create_connection((host, port), timeout=15)
            remote.sendall(fwd.encode())

            # Read response headers
            resp_data = b""
            while b"\r\n\r\n" not in resp_data:
                chunk = remote.recv(4096)
                if not chunk:
                    break
                resp_data += chunk

            header_end = resp_data.find(b"\r\n\r\n")
            if header_end < 0:
                client_sock.sendall(resp_data)
                remote.close()
                client_sock.close()
                return

            headers = resp_data[:header_end].decode("utf-8", errors="replace")
            body_start = header_end + 4
            remaining_body = resp_data[body_start:]

            # Check content type for HTML
            is_html = "text/html" in headers.lower()
            content_length = 0
            cl_match = re.search(r"(?i)content-length:\s*(\d+)", headers)
            if cl_match:
                content_length = int(cl_match.group(1))
            transfer_chunked = "transfer-encoding: chunked" in headers.lower()

            # Clean forward - no banner injection
            client_sock.sendall(resp_data)
            while True:
                chunk = remote.recv(65535)
                if not chunk:
                    break
                client_sock.sendall(chunk)
            # Banner injection disabled
            if False:
                body = remaining_body
                if transfer_chunked:
                    body_chunks = [remaining_body]
                    while True:
                        chunk = remote.recv(65535)
                        if not chunk:
                            break
                        body_chunks.append(chunk)
                        if chunk.endswith(b"0\r\n\r\n"):
                            break
                    body = b"".join(body_chunks)
                else:
                    to_read = content_length - len(remaining_body)
                    while to_read > 0:
                        chunk = remote.recv(min(to_read, 65535))
                        if not chunk:
                            break
                        body += chunk
                        to_read -= len(chunk)

                # Inject banner after <body> or <body...>
                body_str = body.decode("utf-8", errors="replace")
                inj = re.sub(r"(?i)(<body[^>]*>)", r"\1" + BANNER_HTML, body_str, count=1)
                if BANNER_HTML.encode() not in inj.encode():
                    # no <body> tag, prepend
                    inj = BANNER_HTML + body_str
                new_body = inj.encode("utf-8")

                # Rebuild headers with new content-length
                new_headers = re.sub(
                    r"(?i)content-length:\s*\d+",
                    f"Content-Length: {len(new_body)}",
                    headers
                )
                if "content-length" not in new_headers.lower():
                    new_headers += f"\r\nContent-Length: {len(new_body)}"
                # Remove transfer-encoding chunked
                new_headers = re.sub(r"(?i)transfer-encoding:\s*chunked\r\n", "", new_headers)
                if "transfer-encoding" in new_headers.lower():
                    new_headers = re.sub(r"(?i)transfer-encoding:\s*[a-z]+\r\n", "", new_headers)

                client_sock.sendall(new_headers.encode() + b"\r\n\r\n" + new_body)

            remote.close()
        except Exception as e:
            try:
                client_sock.sendall(
                    f"HTTP/1.1 502 Bad Gateway\r\nContent-Type: text/plain\r\n\r\nProxy error: {e}".encode()
                )
            except:
                pass
    except Exception:
        pass
    finally:
        try: client_sock.close()
        except: pass

def start():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", PROXY_PORT))
    srv.listen(200)
    print(f"Proxy started on port {PROXY_PORT}")
    while True:
        try:
            client, addr = srv.accept()
            threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()
        except Exception as e:
            print("Accept error:", e)

if __name__ == "__main__":
    start()
