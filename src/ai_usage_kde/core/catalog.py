from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDescriptor:
    metric_id: str
    title: str
    short_label: str

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.metric_id,
            "title": self.title,
            "short_label": self.short_label,
        }


METRICS = {
    item.metric_id: item
    for item in (
        MetricDescriptor("session", "Session", "S"),
        MetricDescriptor("weekly", "Weekly", "W"),
        MetricDescriptor("daily", "Daily", "D"),
        MetricDescriptor("sonnet", "Sonnet", "So"),
        MetricDescriptor("fable", "Fable", "F"),
        MetricDescriptor("spark", "Spark", "Sp"),
        MetricDescriptor("spark_weekly", "Spark Weekly", "SpW"),
        MetricDescriptor("total_usage", "Total Usage", "T"),
        MetricDescriptor("auto_usage", "Auto Usage", "A"),
        MetricDescriptor("api_usage", "API Usage", "API"),
        MetricDescriptor("chat", "Chat", "Ch"),
        MetricDescriptor("completions", "Completions", "Co"),
        MetricDescriptor("claude_pool", "Claude", "Cl"),
        MetricDescriptor("claude_pool_weekly", "Claude Weekly", "ClW"),
        MetricDescriptor("extra_usage", "Extra Usage", "E"),
        MetricDescriptor("credits", "Credits", "C"),
    )
}


@dataclass(frozen=True)
class ProviderCatalogEntry:
    provider_id: str
    display_name: str
    executable_names: tuple[str, ...]
    installation_indicators: tuple[str, ...]
    supported_metrics: tuple[str, ...]
    default_metric: str
    color: str

    @property
    def icon(self) -> str:
        return f"provider-{self.provider_id}.svg"

    def as_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "icon": self.icon,
            "executable_names": list(self.executable_names),
            "installation_indicators": list(self.installation_indicators),
            "default_metric": self.default_metric,
            "color": self.color,
            "metrics": [METRICS[metric].as_dict() for metric in self.supported_metrics],
        }


PROVIDER_CATALOG = (
    ProviderCatalogEntry(
        "claude", "Claude Code", ("claude",),
        ("~/.claude", "~/.config/claude"),
        ("session", "weekly", "sonnet", "fable", "extra_usage"),
        "weekly", "#d97757",
    ),
    ProviderCatalogEntry(
        "codex", "Codex", ("codex",),
        ("~/.codex", "~/.config/codex"),
        ("session", "weekly", "spark", "spark_weekly", "credits"),
        "weekly", "#10a37f",
    ),
    ProviderCatalogEntry(
        "cursor", "Cursor", ("cursor", "cursor-agent"),
        ("~/.cursor", "~/.config/Cursor"),
        ("total_usage", "auto_usage", "api_usage"),
        "total_usage", "#5b5bd6",
    ),
    ProviderCatalogEntry(
        "antigravity", "Antigravity", ("antigravity", "agy", "agy-ide"),
        ("~/.config/Antigravity", "~/.antigravity"),
        ("session", "weekly", "claude_pool", "claude_pool_weekly"),
        "weekly", "#4285f4",
    ),
    ProviderCatalogEntry(
        "copilot", "GitHub Copilot", ("copilot", "github-copilot"),
        ("~/.config/github-copilot/apps.json", "~/.config/github-copilot/hosts.json"),
        ("credits", "chat", "completions"),
        "credits", "#8957e5",
    ),
    ProviderCatalogEntry(
        "devin", "Devin", ("devin",),
        ("~/.local/share/devin", "~/.config/Devin"),
        ("daily", "weekly"),
        "weekly", "#2f81f7",
    ),
    ProviderCatalogEntry(
        "grok", "Grok", ("grok",),
        ("~/.grok",),
        ("weekly",),
        "weekly", "#111111",
    ),
)

CATALOG_BY_ID = {entry.provider_id: entry for entry in PROVIDER_CATALOG}
PROVIDER_IDS = tuple(CATALOG_BY_ID)


def catalog_json() -> list[dict]:
    return [entry.as_dict() for entry in PROVIDER_CATALOG]
