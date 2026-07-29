import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.kirigami as Kirigami
import "ProviderCatalog.js" as Catalog

PlasmoidItem {
    id: root

    property var snapshot: ({
        "schema_version": 2,
        "catalog": Catalog.providers,
        "installed_provider_ids": [],
        "providers": []
    })
    property var providerStates: ({})
    property var lastGoodProviders: ({})
    property var cooldownUntil: ({})
    property bool hasData: false
    property string lastError: ""
    property date lastUpdate: new Date(0)
    property var updateInfo: null
    property string updateError: ""
    property bool updateChecking: false

    readonly property int refreshInterval: normalizedRefresh(
        Plasmoid.configuration.refreshInterval || 300
    )
    readonly property string usageMode:
        Plasmoid.configuration.usageMode === "used" ? "used" : "remaining"
    readonly property var trackedProviders: configuredList(
        Plasmoid.configuration.trackedProviders,
        Catalog.providerIds()
    )
    readonly property var panelProviders: configuredList(
        Plasmoid.configuration.panelProviders,
        ["claude", "codex"]
    )
    readonly property var configuredMetrics: configuredObject(
        Plasmoid.configuration.providerMetrics,
        {"claude": ["weekly"], "codex": ["weekly"]}
    )
    readonly property var compactGroups: compactProviderGroups()
    readonly property color normalUsageColor: {
        var background = Kirigami.Theme.backgroundColor
        var luminance = background.r * 0.2126
            + background.g * 0.7152
            + background.b * 0.0722
        return luminance < 0.5 ? "#32c7d3" : "#008c95"
    }

    function configuredList(value, fallback) {
        try {
            var parsed = JSON.parse(value || "")
            if (Array.isArray(parsed))
                return parsed.filter(function (id) { return Catalog.byId(id) !== null })
        } catch (error) {
        }
        return fallback.slice()
    }

    function configuredObject(value, fallback) {
        try {
            var parsed = JSON.parse(value || "")
            if (parsed && typeof parsed === "object" && !Array.isArray(parsed))
                return parsed
        } catch (error) {
        }
        return fallback
    }

    function normalizedRefresh(value) {
        var choices = [60, 300, 900, 1800, 3600]
        var closest = choices[0]
        for (var index = 1; index < choices.length; index++) {
            if (Math.abs(choices[index] - value) < Math.abs(closest - value))
                closest = choices[index]
        }
        return closest
    }

    function selectedMetrics(providerId) {
        var configured = root.configuredMetrics[providerId]
        if (!Array.isArray(configured))
            return []
        return configured.filter(function (metricId) {
            return Catalog.metric(providerId, metricId) !== null
        })
    }

    function provider(providerId) {
        return root.providerStates[providerId] || null
    }

    function windowFor(providerData, metricId) {
        var windows = providerData && providerData.windows ? providerData.windows : []
        for (var index = 0; index < windows.length; index++) {
            if (windows[index].kind === metricId)
                return windows[index]
        }
        return null
    }

    function metricReading(providerData, metricId) {
        var window = windowFor(providerData, metricId)
        if (window) {
            return {
                type: "percentage",
                raw_used: Number(window.used_percent),
                value: displayedPercent(Number(window.used_percent))
            }
        }
        var billing = providerData ? providerData.billing_usage : null
        if (!billing)
            return null
        if (metricId === "extra_usage"
                && (billing.kind === "bounded_spend"
                    || billing.kind === "unbounded_spend")) {
            var amount = Number(billing.used_amount || 0)
            if (root.usageMode === "remaining" && billing.kind === "bounded_spend")
                amount = Math.max(Number(billing.limit_amount || 0) - amount, 0)
            return {
                type: "money",
                value: amount,
                currency: billing.currency_code || "USD"
            }
        }
        if (metricId === "credits" && billing.kind === "flex_credit_balance") {
            return {
                type: "credits",
                value: Number(billing.remaining_credits || 0),
                usd: Number(billing.usd_value || 0)
            }
        }
        return null
    }

    function displayedPercent(rawUsed) {
        if (root.usageMode === "used")
            return rawUsed
        return 100 - Math.max(0, Math.min(100, rawUsed))
    }

    function formatReading(reading) {
        if (!reading)
            return "—"
        if (reading.type === "percentage")
            return Math.round(reading.value) + "%"
        if (reading.type === "money")
            return "$" + Number(reading.value).toFixed(2)
        if (reading.type === "credits")
            return String(Math.round(reading.value))
        return "—"
    }

    function barColor(rawUsed) {
        if (rawUsed >= 85)
            return Kirigami.Theme.negativeTextColor
        if (rawUsed >= 60)
            return Kirigami.Theme.neutralTextColor
        return root.normalUsageColor
    }

    function valueColor(rawUsed) {
        if (rawUsed >= 85)
            return Kirigami.Theme.negativeTextColor
        if (rawUsed >= 60)
            return Kirigami.Theme.neutralTextColor
        return Kirigami.Theme.textColor
    }

    function providerIconSource(providerId) {
        var descriptor = Catalog.byId(providerId)
        return descriptor
            ? Qt.resolvedUrl("../images/" + descriptor.icon)
            : "speedometer"
    }

    function compactProviderGroups() {
        var result = []
        var installed = root.snapshot.installed_provider_ids || []
        for (var index = 0; index < root.panelProviders.length; index++) {
            var providerId = root.panelProviders[index]
            if (installed.indexOf(providerId) < 0)
                continue
            var metrics = root.selectedMetrics(providerId)
            if (metrics.length === 0)
                continue
            result.push({
                provider_id: providerId,
                descriptor: Catalog.byId(providerId),
                provider: root.provider(providerId),
                metrics: metrics
            })
        }
        return result
    }

    function activeProviderIds() {
        var now = Date.now()
        var installed = root.snapshot.installed_provider_ids || []
        var knownInstallations = root.hasData
        var result = []
        for (var index = 0; index < root.trackedProviders.length; index++) {
            var providerId = root.trackedProviders[index]
            if (knownInstallations && installed.indexOf(providerId) < 0)
                continue
            var retry = Number(root.cooldownUntil[providerId] || 0)
            if (retry > now)
                continue
            result.push(providerId)
        }
        return result
    }

    function refresh() {
        var providerIds = activeProviderIds()
        if (root.hasData && providerIds.length === 0)
            return
        usageSource.connectSource(
            "python3 -m ai_usage_kde --json --providers=" + providerIds.join(",")
        )
    }

    function applySnapshot(payload) {
        if (!payload || payload.schema_version !== 2)
            throw new Error("Unsupported helper schema")
        var states = Object.assign({}, root.providerStates)
        var goods = Object.assign({}, root.lastGoodProviders)
        var cooldowns = Object.assign({}, root.cooldownUntil)
        var results = payload.providers || []
        for (var index = 0; index < results.length; index++) {
            var current = results[index]
            var providerId = current.provider_id
            if (current.status === "ok") {
                current.stale = false
                states[providerId] = current
                goods[providerId] = current
                delete cooldowns[providerId]
                continue
            }
            var preserves = current.failure_kind === "transient"
                || current.failure_kind === "rate_limited"
                || current.failure_kind === "invalid_response"
            if (preserves && goods[providerId]) {
                states[providerId] = Object.assign({}, goods[providerId], {
                    status: "stale",
                    stale: true,
                    failure_kind: current.failure_kind,
                    error_message: current.error_message,
                    retry_at: current.retry_at
                })
            } else {
                current.stale = false
                states[providerId] = current
                if (!preserves)
                    delete goods[providerId]
            }
            if (current.failure_kind === "rate_limited" && current.retry_at)
                cooldowns[providerId] = new Date(current.retry_at).getTime()
        }

        var installed = payload.installed_provider_ids || []
        var visible = []
        var catalog = payload.catalog && payload.catalog.length
            ? payload.catalog : Catalog.providers
        for (var catalogIndex = 0; catalogIndex < catalog.length; catalogIndex++) {
            var descriptor = catalog[catalogIndex]
            if (installed.indexOf(descriptor.provider_id) >= 0
                    && root.trackedProviders.indexOf(descriptor.provider_id) >= 0
                    && states[descriptor.provider_id]) {
                visible.push(states[descriptor.provider_id])
            }
        }
        root.providerStates = states
        root.lastGoodProviders = goods
        root.cooldownUntil = cooldowns
        root.snapshot = {
            schema_version: 2,
            generated_at: payload.generated_at,
            catalog: catalog,
            installed_provider_ids: installed,
            providers: visible
        }
        root.hasData = true
        root.lastError = ""
        root.lastUpdate = new Date()
    }

    function rebuildVisibleProviders() {
        if (!root.hasData)
            return
        var installed = root.snapshot.installed_provider_ids || []
        var catalog = root.snapshot.catalog || Catalog.providers
        var visible = []
        for (var index = 0; index < catalog.length; index++) {
            var providerId = catalog[index].provider_id
            if (installed.indexOf(providerId) >= 0
                    && root.trackedProviders.indexOf(providerId) >= 0
                    && root.providerStates[providerId]) {
                visible.push(root.providerStates[providerId])
            }
        }
        root.snapshot = Object.assign({}, root.snapshot, {providers: visible})
    }

    function setUsageMode(mode) {
        Plasmoid.configuration.usageMode = mode === "used" ? "used" : "remaining"
    }

    function checkForUpdates() {
        root.updateChecking = true
        root.updateError = ""
        updateSource.connectSource("python3 -m ai_usage_kde --check-update")
    }

    function openUpdate() {
        var url = root.updateInfo && root.updateInfo.release_url
            ? root.updateInfo.release_url
            : "https://github.com/burakgon/ai-usage-kde-widget/releases"
        Qt.openUrlExternally(url)
    }

    Plasma5Support.DataSource {
        id: usageSource
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            usageSource.disconnectSource(source)
            var code = data["exit code"]
            var output = (data["stdout"] || "").toString()
            if (code === 0 && output.trim().length > 0) {
                try {
                    root.applySnapshot(JSON.parse(output))
                } catch (error) {
                    root.lastError = i18n("Could not parse helper output")
                }
            } else {
                var errorText = (data["stderr"] || "").toString().trim()
                root.lastError = errorText.length > 0
                    ? errorText.split("\n").pop()
                    : i18n("Helper exited with code %1", code)
            }
        }
    }

    Plasma5Support.DataSource {
        id: updateSource
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            updateSource.disconnectSource(source)
            root.updateChecking = false
            try {
                var payload = JSON.parse((data["stdout"] || "").toString())
                root.updateInfo = payload.update || null
                root.updateError = root.updateInfo && root.updateInfo.error
                    ? root.updateInfo.error : ""
            } catch (error) {
                root.updateError = i18n("Could not check for updates")
            }
        }
    }

    Timer {
        interval: root.refreshInterval * 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    Timer {
        interval: 24 * 60 * 60 * 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.checkForUpdates()
    }

    Timer {
        id: firstRunSettingsTimer
        interval: 1200
        repeat: false
        onTriggered: Plasmoid.internalAction("configure").trigger()
    }

    Component.onCompleted: {
        if (Plasmoid.configuration.refreshInterval !== root.refreshInterval)
            Plasmoid.configuration.refreshInterval = root.refreshInterval
        if (Plasmoid.configuration.configSchemaVersion !== 2)
            Plasmoid.configuration.configSchemaVersion = 2
        if (!Plasmoid.configuration.initialSetupComplete) {
            Plasmoid.configuration.initialSetupComplete = true
            firstRunSettingsTimer.start()
        }
    }

    onTrackedProvidersChanged: {
        root.rebuildVisibleProviders()
        root.refresh()
    }
    onExpandedChanged: if (root.expanded) root.refresh()

    Plasmoid.icon: "speedometer"
    Plasmoid.busy: !root.hasData && root.lastError === ""
    toolTipMainText: i18n("AI Usage")
    toolTipSubText: {
        if (root.lastError !== "" && !root.hasData)
            return i18n("Error: %1", root.lastError)
        if (!root.hasData)
            return i18n("Loading…")
        if (root.compactGroups.length === 0)
            return i18n("No panel metrics selected.")
        var lines = []
        for (var groupIndex = 0; groupIndex < root.compactGroups.length; groupIndex++) {
            var group = root.compactGroups[groupIndex]
            var values = []
            for (var metricIndex = 0; metricIndex < group.metrics.length; metricIndex++) {
                var metricId = group.metrics[metricIndex]
                var metric = Catalog.metric(group.provider_id, metricId)
                values.push(metric.title + " "
                    + root.formatReading(root.metricReading(group.provider, metricId)))
            }
            lines.push(group.descriptor.display_name + ": " + values.join(" · "))
        }
        return lines.join("\n")
    }

    compactRepresentation: CompactRepresentation {}
    fullRepresentation: FullRepresentation {}

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: i18n("Refresh now")
            icon.name: "view-refresh"
            onTriggered: root.refresh()
        },
        PlasmaCore.Action {
            visible: root.updateInfo && root.updateInfo.update_available
            text: i18n("Update available")
            icon.name: "software-update-available"
            onTriggered: root.openUpdate()
        }
    ]
}
