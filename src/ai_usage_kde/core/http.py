from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass
class HttpResponse:
    status: int
    body: bytes
    headers: dict[str, str]

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())


class HttpError(Exception):
    def __init__(self, status: int, message: str = ""):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def http_request(
    method: str,
    url: str,
    headers: Mapping[str, str],
    *,
    body: bytes | None = None,
    timeout: float = 15.0,
) -> HttpResponse:
    req = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(status=resp.status, body=resp.read(),
                                headers={k.lower(): v for k, v in resp.headers.items()})
    except urllib.error.HTTPError as e:
        return HttpResponse(status=e.code, body=e.read() or b"",
                            headers={k.lower(): v for k, v in (e.headers or {}).items()})


def http_get(url: str, headers: dict[str, str], timeout: float = 15.0) -> HttpResponse:
    return http_request("GET", url, headers, timeout=timeout)


def http_post_form(url: str, data: Mapping[str, str] | Iterable[tuple[str, str]],
                   headers: dict[str, str],
                   timeout: float = 15.0) -> HttpResponse:
    payload = urllib.parse.urlencode(
        data,
        quote_via=urllib.parse.quote,
    ).encode("utf-8")
    h = {"Content-Type": "application/x-www-form-urlencoded", **headers}
    return http_request("POST", url, h, body=payload, timeout=timeout)


def http_post_json(url: str, data: Mapping[str, Any], headers: dict[str, str],
                   timeout: float = 15.0) -> HttpResponse:
    payload = json.dumps(data, separators=(",", ":")).encode("utf-8")
    h = {"Content-Type": "application/json", **headers}
    return http_request("POST", url, h, body=payload, timeout=timeout)
