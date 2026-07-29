from __future__ import annotations

import re
from typing import Callable

from .http import HttpResponse, http_get


REPOSITORY = "burakgon/ai-usage-kde-widget"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"


def semver_tuple(value: str) -> tuple:
    match = re.fullmatch(
        r"\s*v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?\s*",
        value,
    )
    if not match:
        raise ValueError(f"Invalid semantic version: {value}")
    prerelease = match.group(4)
    if prerelease is None:
        pre_key = (1,)
    else:
        identifiers = tuple(
            (0, int(item)) if item.isdigit() else (1, item)
            for item in prerelease.split(".")
        )
        pre_key = (0, identifiers)
    return int(match.group(1)), int(match.group(2)), int(match.group(3)), pre_key


def is_newer(latest: str, current: str) -> bool:
    return semver_tuple(latest) > semver_tuple(current)


def check_for_update(
    current_version: str,
    getter: Callable[..., HttpResponse] = http_get,
) -> dict:
    result = {
        "current_version": current_version,
        "latest_version": None,
        "update_available": False,
        "release_url": RELEASES_URL,
        "error": None,
    }
    try:
        response = getter(
            LATEST_RELEASE_URL,
            {
                "Accept": "application/vnd.github+json",
                "User-Agent": f"ai-usage-kde/{current_version}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    except Exception:
        result["error"] = "Update check could not reach GitHub."
        return result
    if response.status == 404:
        # A repository without a first release is already current by definition.
        result["latest_version"] = current_version
        return result
    if not 200 <= response.status < 300:
        result["error"] = f"Update check failed ({response.status})."
        return result
    try:
        body = response.json()
    except (ValueError, UnicodeDecodeError):
        body = None
    tag = body.get("tag_name") if isinstance(body, dict) else None
    page = body.get("html_url") if isinstance(body, dict) else None
    if not isinstance(tag, str):
        result["error"] = "GitHub returned an invalid release."
        return result
    try:
        result["update_available"] = is_newer(tag, current_version)
    except ValueError:
        result["error"] = "GitHub returned an invalid release version."
        return result
    result["latest_version"] = tag.removeprefix("v")
    if isinstance(page, str) and page.startswith("https://github.com/"):
        result["release_url"] = page
    return result
