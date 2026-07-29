.pragma library

var providers = [
    {
        provider_id: "claude", display_name: "Claude Code",
        icon: "provider-claude.svg", color: "#d97757", default_metric: "weekly",
        metrics: [
            { id: "session", title: "Session", short_label: "S" },
            { id: "weekly", title: "Weekly", short_label: "W" },
            { id: "sonnet", title: "Sonnet", short_label: "So" },
            { id: "fable", title: "Fable", short_label: "F" },
            { id: "extra_usage", title: "Extra Usage", short_label: "E" }
        ]
    },
    {
        provider_id: "codex", display_name: "Codex",
        icon: "provider-codex.svg", color: "#10a37f", default_metric: "weekly",
        metrics: [
            { id: "session", title: "Session", short_label: "S" },
            { id: "weekly", title: "Weekly", short_label: "W" },
            { id: "spark", title: "Spark", short_label: "Sp" },
            { id: "spark_weekly", title: "Spark Weekly", short_label: "SpW" },
            { id: "credits", title: "Credits", short_label: "C" }
        ]
    },
    {
        provider_id: "cursor", display_name: "Cursor",
        icon: "provider-cursor.svg", color: "#5b5bd6", default_metric: "total_usage",
        metrics: [
            { id: "total_usage", title: "Total Usage", short_label: "T" },
            { id: "auto_usage", title: "Auto Usage", short_label: "A" },
            { id: "api_usage", title: "API Usage", short_label: "API" }
        ]
    },
    {
        provider_id: "antigravity", display_name: "Antigravity",
        icon: "provider-antigravity.svg", color: "#4285f4", default_metric: "weekly",
        metrics: [
            { id: "session", title: "Session", short_label: "S" },
            { id: "weekly", title: "Weekly", short_label: "W" },
            { id: "claude_pool", title: "Claude", short_label: "Cl" },
            { id: "claude_pool_weekly", title: "Claude Weekly", short_label: "ClW" }
        ]
    },
    {
        provider_id: "copilot", display_name: "GitHub Copilot",
        icon: "provider-copilot.svg", color: "#8957e5", default_metric: "credits",
        metrics: [
            { id: "credits", title: "Credits", short_label: "C" },
            { id: "chat", title: "Chat", short_label: "Ch" },
            { id: "completions", title: "Completions", short_label: "Co" }
        ]
    },
    {
        provider_id: "devin", display_name: "Devin",
        icon: "provider-devin.svg", color: "#2f81f7", default_metric: "weekly",
        metrics: [
            { id: "daily", title: "Daily", short_label: "D" },
            { id: "weekly", title: "Weekly", short_label: "W" }
        ]
    },
    {
        provider_id: "grok", display_name: "Grok",
        icon: "provider-grok.svg", color: "#111111", default_metric: "weekly",
        metrics: [
            { id: "weekly", title: "Weekly", short_label: "W" }
        ]
    }
]

function byId(providerId) {
    for (var index = 0; index < providers.length; index++) {
        if (providers[index].provider_id === providerId)
            return providers[index]
    }
    return null
}

function metric(providerId, metricId) {
    var provider = byId(providerId)
    if (!provider)
        return null
    for (var index = 0; index < provider.metrics.length; index++) {
        if (provider.metrics[index].id === metricId)
            return provider.metrics[index]
    }
    return null
}

function providerIds() {
    var result = []
    for (var index = 0; index < providers.length; index++)
        result.push(providers[index].provider_id)
    return result
}
