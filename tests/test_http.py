import urllib.request
from urllib.parse import urlencode

from ai_usage_kde.core import http


class _FakeResp:
    status = 200

    def read(self):
        return b'{"access_token":"new"}'

    @property
    def headers(self):
        return {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_http_post_form_sends_urlencoded(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=15.0):
        captured["data"] = req.data
        captured["ctype"] = req.headers.get("Content-type")
        captured["method"] = req.get_method()
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    payload = {"grant_type": "refresh_token", "refresh_token": "r"}
    resp = http.http_post_form("https://example.com/token", payload,
                               {"Accept": "application/json"})
    assert captured["method"] == "POST"
    assert captured["ctype"] == "application/x-www-form-urlencoded"
    assert captured["data"] == urlencode(payload).encode()
    assert resp.status == 200
    assert resp.json()["access_token"] == "new"
