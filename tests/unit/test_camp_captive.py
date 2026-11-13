from __future__ import annotations

import http.client
import importlib.util
import threading
from pathlib import Path
from types import ModuleType

import pytest


def _load_module() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "server" / "scripts" / "camp_captive_portal.py"
    spec = importlib.util.spec_from_file_location("camp_captive_portal", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_target_accepts_http_and_https() -> None:
    module = _load_module()
    assert module.validate_target("http://192.168.50.1:18080/camp") == (
        "http://192.168.50.1:18080/camp"
    )
    assert module.validate_target("https://camp.local/camp") == "https://camp.local/camp"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ftp://example.test/",
        "http://",
        "http://user:pass@example.test/",
        "http://example.test/\r\nX-Test: 1",
        "http://example.test:99999/",
        "http://example.test/камп",
    ],
)
def test_validate_target_rejects_unsafe_values(value: str) -> None:
    module = _load_module()
    with pytest.raises(ValueError):
        module.validate_target(value)


def test_captive_portal_redirects_and_has_healthz() -> None:
    module = _load_module()
    target = "http://192.168.50.1:18080/camp"
    server = module.create_server("127.0.0.1", 0, target)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        connection = http.client.HTTPConnection(host, port, timeout=5)
        connection.request(
            "GET",
            "/generate_204",
            headers={"Host": "connectivitycheck.gstatic.com"},
        )
        response = connection.getresponse()
        assert response.status == 302
        assert response.getheader("Location") == target
        response.read()

        connection.request("GET", "/healthz")
        health = connection.getresponse()
        assert health.status == 204
        health.read()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
