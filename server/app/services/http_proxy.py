#!/usr/bin/env python3
"""
Transparent HTTP/HTTPS proxy with captive portal.

- Port 3128: all TCP traffic intercepted via iptables REDIRECT (ports 80 + 443)
- Checks internet_access per client IP via DB
- Internet OFF: returns captive portal redirect (HTTP) or drops connection (HTTPS)
- Internet ON: forwards to public destinations only

The proxy is deliberately restricted to public IP destinations.  In
particular it must never be able to reach loopback, RFC1918, link-local,
multicast or reserved ranges: a proxy user with internet access must not be
able to tunnel into SSH, Docker, metadata services or the local chat server.
"""

from __future__ import annotations

import ipaddress
import os
import select
import socket
import sqlite3
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return min(max(value, minimum), maximum)


PROXY_BIND = os.environ.get("LC_PROXY_BIND", "0.0.0.0").strip() or "0.0.0.0"
PROXY_PORT = _env_int("LC_PROXY_PORT", 3128, minimum=1, maximum=65535)
SERVER_URL = os.environ.get("LC_SERVER_URL", "http://192.168.4.1:18080")
DB_PATH = os.environ.get(
    "LC_DB_PATH",
    "/opt/local-chat-server/data/sqlite/local_chat.db",
)

MAX_CONNECTIONS = _env_int("LC_PROXY_MAX_CONNECTIONS", 128, minimum=1, maximum=1024)
MAX_CONNECTIONS_PER_IP = _env_int(
    "LC_PROXY_MAX_CONNECTIONS_PER_IP", 16, minimum=1, maximum=256
)
MAX_WORKERS = _env_int("LC_PROXY_MAX_WORKERS", 64, minimum=1, maximum=256)
MAX_REQUEST_HEADER_BYTES = _env_int(
    "LC_PROXY_MAX_REQUEST_HEADER_BYTES", 32 * 1024, minimum=4096, maximum=256 * 1024
)
MAX_RESPONSE_HEADER_BYTES = _env_int(
    "LC_PROXY_MAX_RESPONSE_HEADER_BYTES", 64 * 1024, minimum=4096, maximum=512 * 1024
)
CLIENT_READ_TIMEOUT = _env_int(
    "LC_PROXY_CLIENT_READ_TIMEOUT", 15, minimum=1, maximum=300
)
REMOTE_CONNECT_TIMEOUT = _env_int(
    "LC_PROXY_REMOTE_CONNECT_TIMEOUT", 10, minimum=1, maximum=300
)
REMOTE_READ_TIMEOUT = _env_int(
    "LC_PROXY_REMOTE_READ_TIMEOUT", 30, minimum=1, maximum=300
)
RELAY_IDLE_TIMEOUT = _env_int(
    "LC_PROXY_RELAY_IDLE_TIMEOUT", 120, minimum=1, maximum=3600
)

_ALLOWED_PORTS = {
    int(item.strip())
    for item in os.environ.get("LC_PROXY_ALLOWED_PORTS", "80,443").split(",")
    if item.strip().isdigit()
}
if not _ALLOWED_PORTS:
    _ALLOWED_PORTS = {80, 443}

HTTP_METHODS = {
    b"GET",
    b"POST",
    b"HEAD",
    b"PUT",
    b"DELETE",
    b"OPTIONS",
    b"CONNECT",
    b"PATCH",
}
SO_ORIGINAL_DST = 80  # Linux netfilter: SOL_IP / SO_ORIGINAL_DST


class ProxyDestinationDenied(Exception):
    """Destination is not public or not on an allowed port."""


class ConnectionLimiter:
    def __init__(self, *, total: int, per_ip: int) -> None:
        self._total = total
        self._per_ip = per_ip
        self._active = 0
        self._by_ip: dict[str, int] = {}
        self._lock = threading.Lock()

    def acquire(self, ip: str) -> bool:
        with self._lock:
            if self._active >= self._total:
                return False
            if self._by_ip.get(ip, 0) >= self._per_ip:
                return False
            self._active += 1
            self._by_ip[ip] = self._by_ip.get(ip, 0) + 1
            return True

    def release(self, ip: str) -> None:
        with self._lock:
            if self._active > 0:
                self._active -= 1
            current = self._by_ip.get(ip, 0)
            if current <= 1:
                self._by_ip.pop(ip, None)
            else:
                self._by_ip[ip] = current - 1


# Cache IP -> internet_enabled, refreshed every 2s.
ip_cache: dict[str, bool] = {}
cache_ts = 0.0
cache_lock = threading.Lock()


def get_db() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def user_ip_to_id(ip: str) -> int | None:
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT user_id FROM sessions WHERE ip_address = ? "
                "AND revoked_at_ms IS NULL AND expires_at_ms > ? "
                "AND client_kind = 'web' "
                "ORDER BY created_at_ms DESC LIMIT 1",
                (ip, int(time.time() * 1000)),
            ).fetchone()
            return int(row[0]) if row else None
    except Exception:
        return None


def check_internet(ip: str) -> bool:
    global cache_ts
    now = time.time()
    with cache_lock:
        if now - cache_ts > 2:
            ip_cache.clear()
            cache_ts = now
        if ip in ip_cache:
            return ip_cache[ip]

    user_id = user_ip_to_id(ip)
    if user_id is None:
        # No authenticated web session on this client IP: never grant internet.
        enabled = False
    else:
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT enabled FROM internet_access WHERE user_id = ?",
                    (user_id,),
                ).fetchone()
                enabled = bool(row[0]) if row else False
        except Exception:
            enabled = False

    with cache_lock:
        ip_cache[ip] = enabled
    return enabled


def get_original_dst(sock: socket.socket) -> tuple[str, int] | None:
    """Get original destination (ip, port) after iptables REDIRECT."""
    try:
        raw = sock.getsockopt(getattr(socket, "SOL_IP", 0), SO_ORIGINAL_DST, 16)
        port = struct.unpack("!H", raw[2:4])[0]
        ip = socket.inet_ntoa(raw[4:8])
        return ip, port
    except Exception:
        return None


def _parse_authority(value: str, default_port: int) -> tuple[str, int] | None:
    value = (value or "").strip()
    if not value or any(ch.isspace() for ch in value):
        return None
    try:
        parsed = urlsplit("//" + value)
    except ValueError:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    host = (parsed.hostname or "").strip()
    if not host or "%" in host:
        return None
    try:
        port = parsed.port if parsed.port is not None else default_port
    except ValueError:
        return None
    if not 1 <= port <= 65535:
        return None
    return host, port


def _public_addresses(host: str, port: int) -> list[tuple[int, tuple]]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return []

    addresses: list[tuple[int, tuple]] = []
    for family, socktype, proto, _canon, sockaddr in infos:
        if socktype != socket.SOCK_STREAM:
            continue
        try:
            ip_text = str(sockaddr[0]).split("%", 1)[0]
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            return []
        # Reject if any resolved address is not globally routable.  This
        # prevents a hostname from mixing a public and a loopback/private IP.
        if not ip.is_global:
            return []
        addresses.append((family, sockaddr))
    return addresses


def _connect_public(host: str, port: int) -> socket.socket:
    if port not in _ALLOWED_PORTS:
        raise ProxyDestinationDenied("port not allowed")
    addresses = _public_addresses(host, port)
    if not addresses:
        raise ProxyDestinationDenied("destination is not public")

    last_error: OSError | None = None
    for family, sockaddr in addresses:
        remote = socket.socket(family, socket.SOCK_STREAM)
        remote.settimeout(REMOTE_CONNECT_TIMEOUT)
        try:
            remote.connect(sockaddr)
            return remote
        except OSError as exc:
            last_error = exc
            remote.close()
    raise OSError("could not connect to destination") from last_error


def _send_response(
    client: socket.socket,
    status: int,
    reason: str,
    *,
    body: bytes = b"",
    content_type: str = "text/plain; charset=utf-8",
) -> None:
    if body:
        body = body if body.endswith(b"\n") else body + b"\n"
    headers = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Cache-Control: no-store, no-cache, must-revalidate\r\n"
        "Connection: close\r\n\r\n"
    ).encode("latin-1")
    try:
        client.sendall(headers + body)
    except OSError:
        pass


def _send_redirect(client: socket.socket) -> None:
    location = SERVER_URL.replace("\r", "").replace("\n", "")
    response = (
        "HTTP/1.1 302 Found\r\n"
        f"Location: {location}\r\n"
        "Cache-Control: no-store, no-cache, must-revalidate\r\n"
        "Connection: close\r\n\r\n"
    ).encode("latin-1")
    try:
        client.sendall(response)
    except OSError:
        pass


def _relay(a: socket.socket, b: socket.socket) -> None:
    a.settimeout(RELAY_IDLE_TIMEOUT)
    b.settimeout(RELAY_IDLE_TIMEOUT)
    try:
        while True:
            try:
                readable, _, _ = select.select([a, b], [], [], RELAY_IDLE_TIMEOUT)
            except OSError:
                return
            if not readable:
                return
            for source in readable:
                try:
                    chunk = source.recv(65535)
                except OSError:
                    return
                if not chunk:
                    return
                target = b if source is a else a
                try:
                    target.sendall(chunk)
                except OSError:
                    return
    finally:
        try:
            a.close()
        except OSError:
            pass
        try:
            b.close()
        except OSError:
            pass


def _read_request_headers(client: socket.socket, first: bytes) -> bytes | None:
    data = first
    while b"\r\n\r\n" not in data:
        if len(data) > MAX_REQUEST_HEADER_BYTES:
            _send_response(client, 431, "Request Header Fields Too Large")
            return None
        try:
            chunk = client.recv(8192)
        except OSError:
            return None
        if not chunk:
            return None
        data += chunk
    if len(data) > MAX_REQUEST_HEADER_BYTES:
        _send_response(client, 431, "Request Header Fields Too Large")
        return None
    return data


def _split_request(data: bytes) -> tuple[list[str], bytes]:
    header_end = data.find(b"\r\n\r\n")
    if header_end < 0:
        return [], b""
    header_text = data[:header_end].decode("latin-1")
    return header_text.split("\r\n"), data[header_end + 4 :]


def _forward_http(
    client: socket.socket,
    *,
    method: str,
    target: str,
    headers: list[str],
    body: bytes,
) -> None:
    header_map: dict[str, str] = {}
    for line in headers[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        header_map[name.strip().lower()] = value.strip()

    if target.startswith("http://"):
        try:
            parsed = urlsplit(target)
        except ValueError:
            _send_response(client, 400, "Bad Request")
            return
        if parsed.scheme != "http" or parsed.username is not None or parsed.password is not None:
            _send_response(client, 400, "Bad Request")
            return
        host = parsed.hostname or ""
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
    elif target.startswith("/"):
        authority = header_map.get("host", "")
        parsed_authority = _parse_authority(authority, 80)
        if parsed_authority is None:
            _send_response(client, 400, "Bad Request")
            return
        host, port = parsed_authority
        path = target
    else:
        _send_response(client, 400, "Bad Request")
        return

    try:
        remote = _connect_public(host, port)
    except ProxyDestinationDenied:
        _send_response(client, 403, "Forbidden")
        return
    except OSError:
        _send_response(client, 502, "Bad Gateway")
        return

    host_header = f"[{host}]" if ":" in host else host
    if port != 80:
        host_header += f":{port}"

    lines = [f"{method} {path} HTTP/1.1", f"Host: {host_header}"]
    for name, value in header_map.items():
        if name in {
            "host",
            "connection",
            "keep-alive",
            "proxy-authorization",
            "proxy-connection",
        }:
            continue
        if any(ch in value for ch in "\r\n"):
            continue
        lines.append(f"{name}: {value}")
    lines.append("Connection: close")
    request = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")

    try:
        remote.sendall(request + body)
        response = b""
        while b"\r\n\r\n" not in response:
            if len(response) > MAX_RESPONSE_HEADER_BYTES:
                _send_response(client, 502, "Bad Gateway")
                return
            chunk = remote.recv(8192)
            if not chunk:
                break
            response += chunk
        client.sendall(response)
        while True:
            chunk = remote.recv(65535)
            if not chunk:
                break
            client.sendall(chunk)
    except OSError:
        pass
    finally:
        try:
            remote.close()
        except OSError:
            pass


def handle_client(client_sock: socket.socket, client_addr: tuple) -> None:
    client_ip = client_addr[0] if client_addr else "unknown"
    try:
        client_sock.settimeout(CLIENT_READ_TIMEOUT)
        try:
            first = client_sock.recv(8192)
        except OSError:
            return
        if not first:
            return

        has_internet = check_internet(client_ip)
        is_tls = len(first) > 2 and first[0] == 0x16 and first[1] == 0x03

        if is_tls:
            if not has_internet:
                return
            orig = get_original_dst(client_sock)
            if orig is None:
                return
            host, port = orig
            try:
                remote = _connect_public(host, port)
            except (ProxyDestinationDenied, OSError):
                return
            try:
                remote.sendall(first)
                _relay(client_sock, remote)
            except OSError:
                try:
                    remote.close()
                except OSError:
                    pass
            return

        data = _read_request_headers(client_sock, first)
        if data is None:
            return
        lines, body = _split_request(data)
        if not lines:
            _send_response(client_sock, 400, "Bad Request")
            return

        parts = lines[0].split()
        if len(parts) < 2 or not parts[0].encode("latin-1") in HTTP_METHODS:
            _send_response(client_sock, 405, "Method Not Allowed")
            return

        method = parts[0]
        target = parts[1]

        if not has_internet:
            if method == "CONNECT":
                return
            _send_redirect(client_sock)
            return

        if method == "CONNECT":
            parsed = _parse_authority(target, 443)
            if parsed is None:
                _send_response(client_sock, 400, "Bad Request")
                return
            host, port = parsed
            try:
                remote = _connect_public(host, port)
            except ProxyDestinationDenied:
                _send_response(client_sock, 403, "Forbidden")
                return
            except OSError:
                _send_response(client_sock, 502, "Bad Gateway")
                return
            try:
                client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                _relay(client_sock, remote)
            except OSError:
                try:
                    remote.close()
                except OSError:
                    pass
            return

        # Preserve a request body when the client supplied one.  The header
        # reader already consumed the first packet, so use both the remainder
        # and any additional bytes announced by Content-Length.
        content_length = 0
        for line in lines[1:]:
            if line.lower().startswith("content-length:"):
                try:
                    content_length = int(line.split(":", 1)[1].strip())
                except ValueError:
                    content_length = 0
                break
        if content_length > 0:
            body = body[:content_length]
            while len(body) < content_length:
                try:
                    chunk = client_sock.recv(min(65535, content_length - len(body)))
                except OSError:
                    return
                if not chunk:
                    break
                body += chunk

        _forward_http(
            client_sock,
            method=method,
            target=target,
            headers=lines,
            body=body,
        )
    except Exception:
        pass
    finally:
        try:
            client_sock.close()
        except OSError:
            pass


def _serve_connection(
    client: socket.socket,
    addr: tuple,
    limiter: ConnectionLimiter,
) -> None:
    ip = addr[0] if addr else "unknown"
    try:
        handle_client(client, addr)
    finally:
        limiter.release(ip)


def start() -> None:
    limiter = ConnectionLimiter(
        total=MAX_CONNECTIONS,
        per_ip=MAX_CONNECTIONS_PER_IP,
    )
    executor = ThreadPoolExecutor(
        max_workers=MAX_WORKERS,
        thread_name_prefix="lc-proxy",
    )

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((PROXY_BIND, PROXY_PORT))
    srv.listen(MAX_CONNECTIONS)
    srv.settimeout(1.0)
    print(f"Proxy started on {PROXY_BIND}:{PROXY_PORT}")

    while True:
        try:
            client, addr = srv.accept()
        except socket.timeout:
            continue
        except OSError as exc:
            print("Accept error:", exc)
            continue

        ip = addr[0] if addr else "unknown"
        if not limiter.acquire(ip):
            _send_response(client, 503, "Service Unavailable")
            try:
                client.close()
            except OSError:
                pass
            continue
        try:
            executor.submit(_serve_connection, client, addr, limiter)
        except RuntimeError:
            limiter.release(ip)
            try:
                client.close()
            except OSError:
                pass


if __name__ == "__main__":
    start()
