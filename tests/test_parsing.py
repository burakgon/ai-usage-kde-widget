import json
from datetime import datetime, timezone

from ai_usage_kde.core.parsing import (
    decode_json_with_hex_fallback,
    jwt_expiration,
    number,
    provider_datetime,
    retry_datetime,
)


def test_json_hex_fallback_and_number_rules():
    payload = '{"tokens":{"access_token":"abc"}}'
    assert decode_json_with_hex_fallback(payload)["tokens"]["access_token"] == "abc"
    assert decode_json_with_hex_fallback(payload.encode().hex())["tokens"]["access_token"] == "abc"
    assert decode_json_with_hex_fallback("not-json") is None
    assert number(True) is None
    assert number("17.25") == 17.25


def test_provider_datetime_accepts_iso_epoch_seconds_and_milliseconds():
    assert provider_datetime("2027-01-15T12:00:00.123456").tzinfo == timezone.utc
    assert provider_datetime("2027-01-15 12:00:00 UTC").tzinfo == timezone.utc
    assert provider_datetime(1_800_100_000) == datetime.fromtimestamp(
        1_800_100_000,
        tz=timezone.utc,
    )
    assert provider_datetime(1_800_200_000_000) == datetime.fromtimestamp(
        1_800_200_000,
        tz=timezone.utc,
    )


def test_retry_after_and_jwt_expiration():
    now = datetime(2027, 1, 15, tzinfo=timezone.utc)
    assert (retry_datetime("120", now) - now).total_seconds() == 120
    assert (retry_datetime(None, now) - now).total_seconds() == 300

    header = _segment({"alg": "none"})
    payload = _segment({"exp": now.timestamp() + 60})
    assert jwt_expiration(f"{header}.{payload}.") == datetime.fromtimestamp(
        now.timestamp() + 60,
        tz=timezone.utc,
    )


def _segment(value):
    import base64

    raw = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")
