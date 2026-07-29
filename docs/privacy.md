# Privacy

AI Usage reads existing local sign-in state only for providers the user tracks
and that are detected as installed. Credentials are sent only to the matching
provider's first-party OAuth and usage endpoints.

The helper does not print or log access tokens, refresh tokens, API keys,
credential fingerprints, or raw provider responses. Its JSON output contains
only display metadata, quota percentages, billing summaries, plan names, and
timestamps.

Usage snapshots, stale readings, and rate-limit cooldowns live only in the
Plasma widget process. They disappear when Plasma restarts. AI Usage does not
read local chat transcripts and does not keep usage history.

Antigravity is the one provider that requires a derived access-token cache
because its Secret Service entry can contain only a refresh token. That cache
is written to `$XDG_CACHE_HOME/ai-usage-kde/antigravity-auth.json` (falling back
to `~/.cache`) with mode `0600`. It contains a short-lived access token, expiry,
and a SHA-256 refresh-token fingerprint. It never contains the refresh token.

The optional update check contacts GitHub's public Releases API without
credentials. No analytics or telemetry are collected.
