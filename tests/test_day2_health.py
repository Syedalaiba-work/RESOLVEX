"""Part II §5.1: GET /health also verifies Redis and the media server when they are configured."""
from app import main


def test_health_ok_without_part2_dependencies_configured(fresh, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("MEDIA_API_URL", raising=False)
    assert fresh.get("/health").json() == {"status": "ok"}


def test_health_503_when_redis_is_down(fresh, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")  # nothing listens on port 1
    monkeypatch.delenv("MEDIA_API_URL", raising=False)
    r = fresh.get("/health")
    assert r.status_code == 503 and r.json()["error"]["code"] == "NOT_READY"
    assert "redis" in r.json()["error"]["details"]["failed"]


def test_health_503_when_media_server_is_down(fresh, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("MEDIA_API_URL", "http://127.0.0.1:1")
    r = fresh.get("/health")
    assert r.status_code == 503 and r.json()["error"]["details"]["failed"] == ["media"]


def test_health_ok_when_dependencies_answer(fresh, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("MEDIA_API_URL", "http://media:9997")
    monkeypatch.setattr(main, "_redis_ok", lambda url: True)
    monkeypatch.setattr(main, "_media_ok", lambda url: True)
    assert fresh.get("/health").json() == {"status": "ok"}


def test_redis_probe_speaks_resp():
    import socket
    import threading

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        conn, _ = srv.accept()
        assert conn.recv(64).startswith(b"PING")
        conn.sendall(b"+PONG\r\n")
        conn.close()

    t = threading.Thread(target=serve)
    t.start()
    assert main._redis_ok(f"redis://127.0.0.1:{port}/0") is True
    t.join()
    srv.close()


def test_media_probe_treats_http_error_as_reachable(monkeypatch):
    import urllib.error

    def raise_401(*a, **k):
        raise urllib.error.HTTPError("http://media:9997/v3/paths/list", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(main.urllib.request, "urlopen", raise_401)
    assert main._media_ok("http://media:9997") is True
