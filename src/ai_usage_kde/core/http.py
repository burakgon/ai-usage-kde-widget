from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


@dataclass
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self):
        return json.loads(self.body.decode("utf-8"))


class HttpError(Exception):
    def __init__(self, status: int, message: str = ""):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def http_get(url: str, headers: dict[str, str], timeout: float = 15.0) -> HttpResponse:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(status=resp.status, body=resp.read(),
                                headers={k.lower(): v for k, v in resp.headers.items()})
    except urllib.error.HTTPError as e:
        return HttpResponse(status=e.code, body=e.read() or b"",
                            headers={k.lower(): v for k, v in (e.headers or {}).items()})


def http_post_form(url: str, data: dict[str, str], headers: dict[str, str],
                   timeout: float = 15.0) -> HttpResponse:
    payload = urllib.parse.urlencode(data).encode("utf-8")
    h = {"Content-Type": "application/x-www-form-urlencoded", **headers}
    req = urllib.request.Request(url, data=payload, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(status=resp.status, body=resp.read(),
                                headers={k.lower(): v for k, v in resp.headers.items()})
    except urllib.error.HTTPError as e:
        return HttpResponse(status=e.code, body=e.read() or b"",
                            headers={k.lower(): v for k, v in (e.headers or {}).items()})
