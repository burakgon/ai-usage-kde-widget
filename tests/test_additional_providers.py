import base64
import json
import os
import sqlite3
from datetime import datetime, timezone

import pytest

from ai_usage_kde.core.auth import SecretToolStore
from ai_usage_kde.core.environment import LoginShellEnvironment
from ai_usage_kde.core.http import HttpResponse
from ai_usage_kde.core.model import FailureKind, ProviderStatus
from ai_usage_kde.core.sqlite_store import SQLiteStateStore
from ai_usage_kde.providers.antigravity import (
    AntigravityAuthStore,
    AntigravityCredentials,
    AntigravityOAuthClientStore,
    AntigravityProvider,
)
from ai_usage_kde.providers.copilot import CopilotAuthStore, CopilotProvider
from ai_usage_kde.providers.cursor import (
    ACCESS_KEY,
    MEMBERSHIP_KEY,
    REFRESH_KEY,
    CursorAuthStore,
    CursorProvider,
)
from ai_usage_kde.providers.devin import DevinAuthStore, DevinProvider
from ai_usage_kde.providers.grok import GrokAuthStore, GrokProvider


NOW = datetime(2027, 1, 15, tzinfo=timezone.utc)


def response(body, status=200, headers=None):
    return HttpResponse(
        status=status,
        body=json.dumps(body).encode(),
        headers={key.lower(): value for key, value in (headers or {}).items()},
    )


def environment(values=None):
    return LoginShellEnvironment(
        environ={"PATH": "/usr/bin", **(values or {})},
    )


def create_state_database(path, values):
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)"
        )
        connection.executemany(
            "INSERT INTO ItemTable (key, value) VALUES (?, ?)",
            values.items(),
        )


def test_cursor_sqlite_auth_and_compare_and_swap(tmp_path):
    config = tmp_path / "config"
    path = config / "Cursor/User/globalStorage/state.vscdb"
    create_state_database(path, {
        ACCESS_KEY: "old-access",
        REFRESH_KEY: "refresh-token",
        MEMBERSHIP_KEY: "pro",
    })
    store = CursorAuthStore(
        environment({"XDG_CONFIG_HOME": str(config)}),
        secret_store=SecretToolStore(executable=""),
    )
    credentials = store.load()
    assert credentials.access_token == "old-access"
    assert credentials.refresh_token == "refresh-token"
    assert store.save_access_token(credentials, "new-access")
    assert SQLiteStateStore().read(path, ACCESS_KEY) == "new-access"
    assert not store.save_access_token(credentials, "must-not-overwrite")


def test_cursor_mapper_matches_total_auto_api_and_plan():
    usage = response({
        "enabled": True,
        "billingCycleEnd": "2027-02-01T00:00:00Z",
        "planUsage": {
            "totalSpend": 25,
            "limit": 100,
            "autoPercentUsed": 30,
            "apiPercentUsed": 40,
        },
    })
    plan = response({"planInfo": {"planName": "Pro"}})
    mapped = CursorProvider.map(usage, plan, NOW)
    assert mapped.status == ProviderStatus.OK
    assert mapped.plan == "Pro"
    assert {item.kind: item.used_percent for item in mapped.windows} == {
        "total_usage": 25,
        "auto_usage": 30,
        "api_usage": 40,
    }


def test_antigravity_decodes_go_keyring_and_private_cache(tmp_path):
    payload = json.dumps({
        "tokens": {
            "access_token": "expired-access",
            "refresh_token": "refresh-secret",
            "expires_at": "2020-01-01T00:00:00Z",
        }
    }).encode()
    encoded = "go-keyring-base64:" + base64.b64encode(payload).decode()
    credentials = AntigravityAuthStore.decode(encoded)
    assert credentials.refresh_token == "refresh-secret"

    store = AntigravityAuthStore(
        environment({"XDG_CACHE_HOME": str(tmp_path)}),
        secret_store=SecretToolStore(executable=""),
        now=lambda: NOW,
    )
    assert store.cache("derived-access", 3600, credentials.refresh_token)
    text = store.cache_path().read_text()
    assert "refresh-secret" not in text
    assert os.stat(store.cache_path()).st_mode & 0o777 == 0o600
    assert store.usable_access_token(AntigravityCredentials(
        None, credentials.refresh_token, None
    )) == "derived-access"


def test_antigravity_loads_oauth_client_from_installed_bundle(tmp_path):
    client_id = "123-example" + ".apps.googleusercontent.com"
    client_secret = "fake-" + "oauth-client-secret"
    bundle = tmp_path / "main.js"
    bundle.write_text(
        'module="platform/cloudCode/common/oauthClient.js";'
        f'client="{client_id}",secret="{client_secret}",scopes=[]'
    )

    store = AntigravityOAuthClientStore(paths=(bundle,))
    client = store.load()

    assert client is not None
    assert client.client_id == client_id
    assert client.client_secret == client_secret


def test_antigravity_refresh_uses_installed_oauth_client(tmp_path):
    client_id = "123-example" + ".apps.googleusercontent.com"
    client_secret = "fake-" + "oauth-client-secret"
    bundle = tmp_path / "main.js"
    bundle.write_text(
        'module="platform/cloudCode/common/oauthClient.js";'
        f'client="{client_id}",secret="{client_secret}"'
    )
    calls = []

    def post_form(url, fields, headers):
        calls.append((url, fields, headers))
        return response({"access_token": "fresh-access", "expires_in": 3600})

    auth = AntigravityAuthStore(
        environment({"XDG_CACHE_HOME": str(tmp_path)}),
        secret_store=SecretToolStore(executable=""),
        now=lambda: NOW,
    )
    provider = AntigravityProvider(
        auth_store=auth,
        oauth_client_store=AntigravityOAuthClientStore(paths=(bundle,)),
        form_poster=post_form,
        now=lambda: NOW,
    )

    assert provider._refresh("refresh-token") == "fresh-access"
    assert ("client_id", client_id) in calls[0][1]
    assert ("client_secret", client_secret) in calls[0][1]


def test_antigravity_summary_maps_four_quota_buckets():
    summary = response({
        "response": {
            "groups": [{
                "buckets": [
                    {"bucketId": "gemini-5h", "remainingFraction": 0.7},
                    {"bucketId": "gemini-weekly", "remainingFraction": 0.8},
                    {"bucketId": "3p-5h", "remainingFraction": 0.6},
                    {"bucketId": "3p-weekly", "remainingFraction": 0.5},
                ]
            }]
        }
    })
    mapped = AntigravityProvider._map_summary(summary, "Pro", NOW)
    assert mapped.plan == "Pro"
    assert {item.kind: item.used_percent for item in mapped.windows} == {
        "session": 30,
        "weekly": 20,
        "claude_pool": 40,
        "claude_pool_weekly": 50,
    }


def test_copilot_auth_source_order_and_mapper(tmp_path):
    config = tmp_path / "config"
    path = config / "github-copilot/apps.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "github.com": {"oauth_token": "editor-token"}
    }))
    store = CopilotAuthStore(
        environment({"XDG_CONFIG_HOME": str(config)}),
        SecretToolStore(executable=""),
    )
    assert store.load_token() == "editor-token"

    mapped = CopilotProvider.map(response({
        "copilot_plan": "individual_pro",
        "quota_reset_date": "2027-02-01",
        "quota_snapshots": {
            "premium_interactions": {
                "entitlement": 1000,
                "remaining": 750,
                "percent_remaining": 75,
            },
            "chat": {"unlimited": True, "entitlement": -1},
        },
    }), NOW)
    assert mapped.status == ProviderStatus.OK
    assert mapped.plan == "Individual Pro"
    assert [(item.kind, item.used_percent) for item in mapped.windows] == [
        ("credits", 25)
    ]


def test_devin_toml_and_quota_mapper(tmp_path):
    data = tmp_path / "data"
    path = data / "devin/credentials.toml"
    path.parent.mkdir(parents=True)
    path.write_text(
        'windsurf_api_key = "devin-key"\n'
        'api_server_url = "https://example.test/"\n'
    )
    store = DevinAuthStore(environment({"XDG_DATA_HOME": str(data)}))
    credentials = store.load_file()
    assert credentials.api_key == "devin-key"
    assert credentials.server_url == "https://example.test"

    mapped = DevinProvider.map(response({
        "userStatus": {
            "planStatus": {
                "dailyQuotaRemainingPercent": 90,
                "weeklyQuotaRemainingPercent": 55,
                "dailyQuotaResetAtUnix": 1_800_000_000,
                "weeklyQuotaResetAtUnix": 1_800_100_000,
                "planInfo": {"planName": "Teams", "hideDailyQuota": False},
            }
        }
    }), NOW)
    assert mapped.plan == "Teams"
    assert {item.kind: item.used_percent for item in mapped.windows} == {
        "daily": 10,
        "weekly": 45,
    }


def test_grok_source_aware_save_and_weekly_mapper(tmp_path, monkeypatch):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({
        "user::client-id": {
            "key": "access",
            "refresh_token": "refresh",
            "expires_at": "2027-02-01T00:00:00Z",
        }
    }))
    store = GrokAuthStore(now=lambda: NOW)
    monkeypatch.setattr(store, "auth_path", lambda: path)
    credentials = store.load_candidates()[0]
    credentials.entry["key"] = "rotated"
    assert store.save(credentials)
    assert os.stat(path).st_mode & 0o777 == 0o600

    stale = store.load_candidates()[0]
    path.write_text('{"concurrent":{"key":"cli-won"}}')
    stale.entry["key"] = "must-not-win"
    assert not store.save(stale)

    mapped = GrokProvider.map(
        response({
            "config": {
                "currentPeriod": {
                    "type": "USAGE_PERIOD_TYPE_WEEKLY",
                    "end": "2027-02-01T00:00:00Z",
                },
                "creditUsagePercent": 36,
            }
        }),
        response({"subscription_tier_display": "SuperGrok"}),
        NOW,
    )
    assert mapped.status == ProviderStatus.OK
    assert mapped.plan == "SuperGrok"
    assert mapped.windows[0].kind == "weekly"
    assert mapped.windows[0].used_percent == 36


@pytest.mark.parametrize("status,kind", [
    (500, FailureKind.TRANSIENT),
    (400, FailureKind.INVALID_RESPONSE),
])
def test_new_provider_http_failures_are_classified(status, kind):
    mapped = CursorProvider.map(response({}, status=status), None, NOW)
    assert mapped.failure_kind == kind
