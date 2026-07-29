import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kcmutils as KCM
import org.kde.kirigami as Kirigami
import org.kde.plasma.plasmoid
import org.kde.plasma.plasma5support as Plasma5Support
import "ProviderCatalog.js" as Catalog

KCM.ScrollViewKCM {
    id: page

    property string cfg_trackedProviders:
        "[\"claude\",\"codex\",\"cursor\",\"antigravity\",\"copilot\",\"devin\",\"grok\"]"
    property string cfg_trackedProvidersDefault:
        "[\"claude\",\"codex\",\"cursor\",\"antigravity\",\"copilot\",\"devin\",\"grok\"]"
    property string cfg_panelProviders: "[\"claude\",\"codex\"]"
    property string cfg_panelProvidersDefault: "[\"claude\",\"codex\"]"
    property string cfg_providerMetrics:
        "{\"claude\":[\"weekly\"],\"codex\":[\"weekly\"]}"
    property string cfg_providerMetricsDefault:
        "{\"claude\":[\"weekly\"],\"codex\":[\"weekly\"]}"
    property string cfg_usageMode: "remaining"
    property string cfg_usageModeDefault: "remaining"
    property int cfg_refreshInterval: 300
    property int cfg_refreshIntervalDefault: 300
    property int cfg_configSchemaVersion: 2
    property int cfg_configSchemaVersionDefault: 2
    property bool cfg_initialSetupComplete: false
    property bool cfg_initialSetupCompleteDefault: false

    property var catalogModel: Catalog.providers
    property var installedProviderIds: []
    property var providerResults: ({})
    property var updateInfo: null
    property string updateMessage: ""
    property bool checkingProviders: false
    property bool checkingUpdate: false
    readonly property var refreshChoices: [
        { value: 60, text: i18n("1 minute") },
        { value: 300, text: i18n("5 minutes") },
        { value: 900, text: i18n("15 minutes") },
        { value: 1800, text: i18n("30 minutes") },
        { value: 3600, text: i18n("1 hour") }
    ]

    function parseList(value, fallback) {
        try {
            var parsed = JSON.parse(value || "")
            if (Array.isArray(parsed))
                return parsed
        } catch (error) {
        }
        return fallback.slice()
    }

    function parseMetrics() {
        try {
            var parsed = JSON.parse(page.cfg_providerMetrics || "")
            if (parsed && typeof parsed === "object" && !Array.isArray(parsed))
                return parsed
        } catch (error) {
        }
        return {}
    }

    function tracked() {
        return parseList(page.cfg_trackedProviders, Catalog.providerIds())
    }

    function panel() {
        return parseList(page.cfg_panelProviders, ["claude", "codex"])
    }

    function contains(list, value) {
        return list.indexOf(value) >= 0
    }

    function setMembership(list, value, enabled) {
        var result = list.slice()
        var index = result.indexOf(value)
        if (enabled && index < 0)
            result.push(value)
        else if (!enabled && index >= 0)
            result.splice(index, 1)
        return result
    }

    function setTracked(providerId, enabled) {
        page.cfg_trackedProviders = JSON.stringify(
            setMembership(tracked(), providerId, enabled)
        )
        if (!enabled) {
            page.cfg_panelProviders = JSON.stringify(
                setMembership(panel(), providerId, false)
            )
        }
    }

    function selectedMetrics(providerId) {
        var result = parseMetrics()[providerId]
        return Array.isArray(result) ? result : []
    }

    function setPanel(providerId, enabled) {
        var trackedProviders = tracked()
        var panelProviders = panel()
        var metrics = parseMetrics()
        if (enabled) {
            trackedProviders = setMembership(trackedProviders, providerId, true)
            panelProviders = setMembership(panelProviders, providerId, true)
            if (!Array.isArray(metrics[providerId]) || metrics[providerId].length === 0) {
                var descriptor = Catalog.byId(providerId)
                metrics[providerId] = [descriptor.default_metric]
            }
        } else {
            panelProviders = setMembership(panelProviders, providerId, false)
        }
        page.cfg_trackedProviders = JSON.stringify(trackedProviders)
        page.cfg_panelProviders = JSON.stringify(panelProviders)
        page.cfg_providerMetrics = JSON.stringify(metrics)
    }

    function setMetric(providerId, metricId, enabled) {
        var metrics = parseMetrics()
        var selected = Array.isArray(metrics[providerId])
            ? metrics[providerId].slice() : []
        selected = setMembership(selected, metricId, enabled)
        metrics[providerId] = selected
        page.cfg_providerMetrics = JSON.stringify(metrics)
        if (enabled) {
            page.cfg_trackedProviders = JSON.stringify(
                setMembership(tracked(), providerId, true)
            )
            page.cfg_panelProviders = JSON.stringify(
                setMembership(panel(), providerId, true)
            )
        } else if (selected.length === 0) {
            page.cfg_panelProviders = JSON.stringify(
                setMembership(panel(), providerId, false)
            )
        }
    }

    function resultFor(providerId) {
        return page.providerResults[providerId] || null
    }

    function providerStatus(providerId) {
        if (!contains(page.installedProviderIds, providerId))
            return i18n("Not detected")
        var result = resultFor(providerId)
        if (!result)
            return page.checkingProviders ? i18n("Checking…") : i18n("Detected")
        if (result.status === "ok")
            return result.plan ? i18n("Connected · %1", result.plan) : i18n("Connected")
        if (result.status === "stale")
            return i18n("Connected · stale")
        return result.error_message || result.status
    }

    function metricAvailable(providerId, metricId) {
        var result = resultFor(providerId)
        return !result || !Array.isArray(result.available_metrics)
            || contains(result.available_metrics, metricId)
    }

    function normalizedRefresh(value) {
        var best = page.refreshChoices[0].value
        for (var index = 1; index < page.refreshChoices.length; index++) {
            var candidate = page.refreshChoices[index].value
            if (Math.abs(candidate - value) < Math.abs(best - value))
                best = candidate
        }
        return best
    }

    function refreshIndex(value) {
        for (var index = 0; index < page.refreshChoices.length; index++) {
            if (page.refreshChoices[index].value === value)
                return index
        }
        return 1
    }

    function refreshProviders() {
        page.checkingProviders = true
        var safe = tracked().filter(function (providerId) {
            return Catalog.byId(providerId) !== null
        })
        providerSource.connectSource(
            "python3 -m ai_usage_kde --json --providers=" + safe.join(",")
        )
    }

    function checkForUpdates() {
        page.checkingUpdate = true
        page.updateMessage = ""
        updateSource.connectSource("python3 -m ai_usage_kde --check-update")
    }

    Component.onCompleted: {
        page.cfg_refreshInterval = normalizedRefresh(page.cfg_refreshInterval)
        page.cfg_configSchemaVersion = 2
        page.cfg_initialSetupComplete = true
        Qt.callLater(page.refreshProviders)
    }

    Plasma5Support.DataSource {
        id: providerSource
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            providerSource.disconnectSource(source)
            page.checkingProviders = false
            try {
                var payload = JSON.parse((data["stdout"] || "").toString())
                if (payload.schema_version !== 2)
                    throw new Error("schema")
                if (payload.catalog && payload.catalog.length)
                    page.catalogModel = payload.catalog
                page.installedProviderIds = payload.installed_provider_ids || []
                var results = {}
                var providers = payload.providers || []
                for (var index = 0; index < providers.length; index++)
                    results[providers[index].provider_id] = providers[index]
                page.providerResults = results
            } catch (error) {
                page.updateMessage = i18n("Could not read provider status.")
            }
        }
    }

    Plasma5Support.DataSource {
        id: updateSource
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            updateSource.disconnectSource(source)
            page.checkingUpdate = false
            try {
                var payload = JSON.parse((data["stdout"] || "").toString())
                page.updateInfo = payload.update || null
                if (page.updateInfo.error)
                    page.updateMessage = page.updateInfo.error
                else if (page.updateInfo.update_available)
                    page.updateMessage = i18n(
                        "Version %1 is available.",
                        page.updateInfo.latest_version
                    )
                else
                    page.updateMessage = i18n("AI Usage is up to date.")
            } catch (error) {
                page.updateMessage = i18n("Could not check for updates.")
            }
        }
    }

    view: ListView {
        id: providerList
        clip: true
        spacing: Kirigami.Units.smallSpacing
        model: page.catalogModel

        header: ColumnLayout {
            width: providerList.width
            spacing: Kirigami.Units.largeSpacing

            Kirigami.Heading {
                level: 2
                text: i18n("General")
            }

            Kirigami.FormLayout {
                Layout.fillWidth: true

                QQC2.ComboBox {
                    Kirigami.FormData.label: i18n("Display:")
                    model: [i18n("Left"), i18n("Used")]
                    currentIndex: page.cfg_usageMode === "used" ? 1 : 0
                    onActivated: page.cfg_usageMode = currentIndex === 1
                        ? "used" : "remaining"
                }

                QQC2.ComboBox {
                    Kirigami.FormData.label: i18n("Refresh every:")
                    textRole: "text"
                    valueRole: "value"
                    model: page.refreshChoices
                    currentIndex: page.refreshIndex(page.cfg_refreshInterval)
                    onActivated: page.cfg_refreshInterval = currentValue
                }

                QQC2.Label {
                    Kirigami.FormData.label: i18n("Startup:")
                    text: i18n(
                        "Starts with Plasma while this widget remains on a panel."
                    )
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Kirigami.Heading {
                    Layout.fillWidth: true
                    level: 2
                    text: i18n("Providers")
                }
                QQC2.Button {
                    text: page.checkingProviders ? i18n("Checking…") : i18n("Refresh status")
                    icon.name: "view-refresh"
                    enabled: !page.checkingProviders
                    onClicked: page.refreshProviders()
                }
            }
        }

        delegate: Rectangle {
            id: providerRow
            required property var modelData
            width: providerList.width
            implicitHeight: providerColumn.implicitHeight
                + Kirigami.Units.largeSpacing * 2
            radius: Kirigami.Units.smallSpacing
            color: Qt.rgba(
                Kirigami.Theme.textColor.r,
                Kirigami.Theme.textColor.g,
                Kirigami.Theme.textColor.b,
                0.045
            )

            ColumnLayout {
                id: providerColumn
                anchors {
                    left: parent.left
                    right: parent.right
                    top: parent.top
                    margins: Kirigami.Units.largeSpacing
                }
                spacing: Kirigami.Units.smallSpacing

                RowLayout {
                    Layout.fillWidth: true

                    Kirigami.Icon {
                        source: Qt.resolvedUrl(
                            "../images/" + providerRow.modelData.icon
                        )
                        Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                        Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                        isMask: true
                        color: Kirigami.Theme.textColor
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0
                        Kirigami.Heading {
                            Layout.fillWidth: true
                            level: 4
                            text: providerRow.modelData.display_name
                            elide: Text.ElideRight
                        }
                        QQC2.Label {
                            Layout.fillWidth: true
                            text: page.providerStatus(
                                providerRow.modelData.provider_id
                            )
                            opacity: 0.62
                            elide: Text.ElideRight
                            font: Kirigami.Theme.smallFont
                        }
                    }
                    QQC2.Switch {
                        text: i18n("Track")
                        checked: page.contains(
                            page.tracked(),
                            providerRow.modelData.provider_id
                        )
                        onClicked: page.setTracked(
                            providerRow.modelData.provider_id,
                            checked
                        )
                    }
                    QQC2.Switch {
                        text: i18n("Panel")
                        checked: page.contains(
                            page.panel(),
                            providerRow.modelData.provider_id
                        )
                        onClicked: page.setPanel(
                            providerRow.modelData.provider_id,
                            checked
                        )
                    }
                }

                Flow {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    Repeater {
                        model: providerRow.modelData.metrics || []

                        delegate: QQC2.CheckBox {
                            id: metricCheck
                            required property var modelData
                            text: page.metricAvailable(
                                providerRow.modelData.provider_id,
                                metricCheck.modelData.id
                            )
                                ? metricCheck.modelData.title
                                : i18n("%1 (unavailable)", metricCheck.modelData.title)
                            opacity: page.metricAvailable(
                                providerRow.modelData.provider_id,
                                metricCheck.modelData.id
                            ) ? 1 : 0.65
                            checked: page.contains(
                                page.selectedMetrics(
                                    providerRow.modelData.provider_id
                                ),
                                metricCheck.modelData.id
                            )
                            onClicked: page.setMetric(
                                providerRow.modelData.provider_id,
                                metricCheck.modelData.id,
                                checked
                            )
                        }
                    }
                }
            }
        }

        footer: ColumnLayout {
            width: providerList.width
            spacing: Kirigami.Units.largeSpacing

            Kirigami.Separator {
                Layout.fillWidth: true
            }
            Kirigami.Heading {
                level: 2
                text: i18n("About")
            }
            QQC2.Label {
                Layout.fillWidth: true
                text: i18n("AI Usage 2.0.0")
                font.bold: true
            }
            QQC2.Label {
                Layout.fillWidth: true
                text: i18n(
                    "Credentials stay on this computer. The helper only contacts each provider's usage API and GitHub when checking for updates."
                )
                wrapMode: Text.WordWrap
                opacity: 0.72
            }
            RowLayout {
                Layout.fillWidth: true
                QQC2.Button {
                    text: i18n("Check for Updates")
                    icon.name: "software-update-available"
                    enabled: !page.checkingUpdate
                    onClicked: page.checkForUpdates()
                }
                QQC2.Button {
                    text: i18n("Open GitHub")
                    icon.name: "internet-services"
                    onClicked: Qt.openUrlExternally(
                        "https://github.com/burakgon/ai-usage-kde-widget"
                    )
                }
                Item {
                    Layout.fillWidth: true
                }
                QQC2.Button {
                    text: i18n("Remove Widget…")
                    icon.name: "edit-delete"
                    onClicked: {
                        var dialog = removeDialogFactory.createObject(page)
                        if (dialog)
                            dialog.open()
                    }
                }
            }
            QQC2.Label {
                visible: page.updateMessage !== ""
                Layout.fillWidth: true
                text: page.updateMessage
                wrapMode: Text.WordWrap
                opacity: 0.72
            }
            Item {
                implicitHeight: Kirigami.Units.largeSpacing
            }
        }
    }

    Component {
        id: removeDialogFactory

        QQC2.Dialog {
            parent: page
            anchors.centerIn: parent
            modal: true
            title: i18n("Remove AI Usage?")
            standardButtons: QQC2.Dialog.Cancel | QQC2.Dialog.Ok
            onAccepted: Plasmoid.internalAction("remove").trigger()
            onClosed: destroy()

            QQC2.Label {
                width: Kirigami.Units.gridUnit * 18
                text: i18n(
                    "This removes the widget from the panel. Provider credentials are not changed."
                )
                wrapMode: Text.WordWrap
            }
        }
    }
}
