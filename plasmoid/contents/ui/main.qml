import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    // Parsed output of `python3 -m ai_usage_kde --json`.
    property var snapshot: ({ "providers": [], "local_claude": null })
    property bool hasData: false
    property string lastError: ""
    property date lastUpdate: new Date(0)

    readonly property int refreshInterval: 180  // seconds (safe poll rate)

    // Highest session-window % across providers — drives the panel badge.
    readonly property int maxSession: {
        var best = 0
        var ps = snapshot.providers || []
        for (var i = 0; i < ps.length; i++) {
            var ws = ps[i].windows || []
            for (var j = 0; j < ws.length; j++)
                if (ws[j].kind === "session")
                    best = Math.max(best, ws[j].used_percent)
        }
        return Math.round(best)
    }

    // Theme-adaptive threshold color (follows the user's accent/scheme).
    function barColor(pct) {
        if (pct >= 85) return Kirigami.Theme.negativeTextColor
        if (pct >= 60) return Kirigami.Theme.neutralTextColor
        return Kirigami.Theme.highlightColor
    }

    Plasmoid.icon: "speedometer"
    Plasmoid.busy: !hasData && lastError === ""

    toolTipMainText: i18n("AI Usage")
    toolTipSubText: {
        if (lastError !== "" && !hasData) return i18n("Error: %1", lastError)
        if (!hasData) return i18n("Loading…")
        var lines = []
        var ps = snapshot.providers || []
        for (var i = 0; i < ps.length; i++) {
            var p = ps[i]
            if (p.status === "ok") {
                var sess = "—", wk = "—"
                var ws = p.windows || []
                for (var j = 0; j < ws.length; j++) {
                    if (ws[j].kind === "session") sess = Math.round(ws[j].used_percent) + "%"
                    if (ws[j].kind === "weekly") wk = Math.round(ws[j].used_percent) + "%"
                }
                lines.push(p.display_name + ": " + sess + " / " + wk)
            } else {
                lines.push(p.display_name + ": " + (p.error_message || p.status))
            }
        }
        lines.push("")
        lines.push(i18n("Updated %1 · every %2s",
                        Qt.formatTime(lastUpdate, "HH:mm:ss"), refreshInterval))
        return lines.join("\n")
    }

    Plasma5Support.DataSource {
        id: executable
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            executable.disconnectSource(source)
            var code = data["exit code"]
            var out = (data["stdout"] || "").toString()
            if (code === 0 && out.trim().length > 0) {
                try {
                    root.snapshot = JSON.parse(out)
                    root.hasData = true
                    root.lastError = ""
                    root.lastUpdate = new Date()
                } catch (e) {
                    root.lastError = i18n("Could not parse helper output")
                }
            } else {
                var err = (data["stderr"] || "").toString().trim()
                root.lastError = err.length > 0 ? err.split("\n").pop()
                                                : i18n("Helper exited with code %1", code)
            }
        }
    }

    function refresh() {
        executable.connectSource("python3 -m ai_usage_kde --json")
    }

    Timer {
        interval: root.refreshInterval * 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refresh()
    }

    // Refresh sooner when the popup is opened.
    onExpandedChanged: if (root.expanded) root.refresh()

    compactRepresentation: CompactRepresentation {}
    fullRepresentation: FullRepresentation {}

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: i18n("Refresh now")
            icon.name: "view-refresh"
            onTriggered: root.refresh()
        }
    ]
}
