#!/usr/bin/env python3
"""Camp Edition captive portal responder.

The access point is provided by hostapd/dnsmasq.  dnsmasq resolves every name
to the camp server, and this tiny HTTP server answers port 80 with a redirect to
the Camp Edition UI.  Phones/tablets then show their standard "sign in to
network" sheet instead of requiring the user to type an IP address.

This process deliberately does not proxy, inspect or modify client traffic.  It
only returns a 302 to an operator-configured URL.
"""

from __future__ import annotations

import argparse
import http.server
import sys
from urllib.parse import urlsplit

DEFAULT_TARGET = "http://192.168.50.1:18080/camp"


def validate_target(value: str) -> str:
    """Return a safe redirect target or raise ValueError."""
    text = str(value or "").strip()
    if not text or "\r" in text or "\n" in text or not text.isascii():
        raise ValueError("target must be a single ASCII URL")
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("target must use http:// or https://")
    if not parsed.hostname:
        raise ValueError("target must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("target must not include credentials")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("target has an invalid port") from exc
    if port is not None and not (1 <= port <= 65535):
        raise ValueError("target has an invalid port")
    return text


class CaptivePortalHandler(http.server.BaseHTTPRequestHandler):
    server_version = "CampCaptive/1.0"
    portal_target = DEFAULT_TARGET
    health_path = "/healthz"

    def _redirect(self) -> None:
        self.send_response(302)
        self.send_header("Location", self.portal_target)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    def _health(self) -> None:
        self.send_response(204)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        if urlsplit(self.path).path == self.health_path:
            self._health()
            return
        self._redirect()

    def do_HEAD(self) -> None:  # noqa: N802
        if urlsplit(self.path).path == self.health_path:
            self._health()
            return
        self._redirect()

    def do_POST(self) -> None:  # noqa: N802
        self._redirect()

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.address_string(), self.log_date_time_string(), format % args)
        )


def build_handler(target: str) -> type[CaptivePortalHandler]:
    safe_target = validate_target(target)

    class Handler(CaptivePortalHandler):
        portal_target = safe_target

    return Handler


def create_server(
    listen: str,
    port: int,
    target: str,
) -> http.server.ThreadingHTTPServer:
    if not (0 <= int(port) <= 65535):
        raise ValueError("port must be 0..65535")
    handler = build_handler(target)
    server = http.server.ThreadingHTTPServer((listen, int(port)), handler)
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Camp Edition captive portal")
    parser.add_argument("--listen", default="0.0.0.0", help="bind address")
    parser.add_argument("--port", type=int, default=80, help="TCP port (default 80)")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="redirect URL")
    args = parser.parse_args(argv)

    try:
        server = create_server(args.listen, args.port, args.target)
    except (OSError, ValueError) as exc:
        print(f"camp-captive-portal: {exc}", file=sys.stderr)
        return 2

    print(
        f"camp-captive-portal: listening on {args.listen}:{args.port} -> {args.target}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
