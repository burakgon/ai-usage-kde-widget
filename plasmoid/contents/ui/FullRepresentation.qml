import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami

PlasmaExtras.Representation {
    id: full

    Layout.minimumWidth: Kirigami.Units.gridUnit * 17
    Layout.minimumHeight: Kirigami.Units.gridUnit * 12
    Layout.preferredWidth: Kirigami.Units.gridUnit * 19
    Layout.preferredHeight: Kirigami.Units.gridUnit * 23

    header: PlasmaExtras.PlasmoidHeading {
        RowLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing
            Kirigami.Heading {
                Layout.fillWidth: true
                level: 2
                text: i18n("AI Usage")
                elide: Text.ElideRight
            }
            PlasmaComponents.ToolButton {
                icon.name: "view-refresh"
                display: QQC2.AbstractButton.IconOnly
                onClicked: root.refresh()
                QQC2.ToolTip.text: i18n("Refresh now")
                QQC2.ToolTip.visible: hovered
            }
            PlasmaComponents.ToolButton {
                icon.name: "configure"
                display: QQC2.AbstractButton.IconOnly
                onClicked: Plasmoid.internalAction("configure").trigger()
                QQC2.ToolTip.text: i18n("Configure…")
                QQC2.ToolTip.visible: hovered
            }
        }
    }

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.largeSpacing

        PlasmaExtras.PlaceholderMessage {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.hasData && root.lastError !== ""
            iconName: "network-disconnect"
            text: i18n("Couldn't load usage")
            explanation: root.lastError
        }

        PlasmaExtras.PlaceholderMessage {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: !root.hasData && root.lastError === ""
            iconName: "speedometer"
            text: i18n("Loading…")
        }

        Repeater {
            model: root.hasData ? (root.snapshot.providers || []) : []

            delegate: ColumnLayout {
                id: section
                required property var modelData
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing

                // provider header: brand marker + name + plan
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    Rectangle {
                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                        Layout.preferredHeight: Kirigami.Units.iconSizes.small
                        radius: Kirigami.Units.smallSpacing
                        color: section.modelData.provider_id === "claude" ? "#d97757" : "#10a37f"
                        PlasmaComponents.Label {
                            anchors.centerIn: parent
                            text: section.modelData.provider_id === "claude" ? "C" : "O"
                            color: "#ffffff"
                            font.bold: true
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize
                        }
                    }
                    Kirigami.Heading {
                        level: 4
                        text: section.modelData.display_name
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                    PlasmaComponents.Label {
                        visible: !!section.modelData.plan
                        text: section.modelData.plan || ""
                        opacity: 0.7
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize
                    }
                }

                PlasmaComponents.Label {
                    Layout.fillWidth: true
                    visible: section.modelData.status !== "ok"
                    text: section.modelData.error_message || section.modelData.status
                    opacity: 0.7
                    wrapMode: Text.WordWrap
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize
                }

                Repeater {
                    model: section.modelData.windows || []
                    delegate: ColumnLayout {
                        id: win
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 2

                        RowLayout {
                            Layout.fillWidth: true
                            PlasmaComponents.Label {
                                text: win.modelData.caption
                                opacity: 0.85
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize
                            }
                            Item { Layout.fillWidth: true }
                            PlasmaComponents.Label {
                                text: Math.round(win.modelData.used_percent) + "%"
                                font.bold: true
                                color: root.barColor(win.modelData.used_percent)
                                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            height: Math.round(Kirigami.Units.gridUnit * 0.35)
                            radius: height / 2
                            color: Qt.rgba(Kirigami.Theme.textColor.r,
                                           Kirigami.Theme.textColor.g,
                                           Kirigami.Theme.textColor.b, 0.15)
                            Rectangle {
                                width: parent.width * Math.max(0, Math.min(1, win.modelData.used_percent / 100))
                                height: parent.height
                                radius: height / 2
                                color: root.barColor(win.modelData.used_percent)
                                Behavior on width { NumberAnimation { duration: 300; easing.type: Easing.OutCubic } }
                            }
                        }

                        PlasmaComponents.Label {
                            visible: !!win.modelData.resets_at
                            text: full.resetText(win.modelData.resets_at)
                            opacity: 0.55
                            font.pixelSize: Kirigami.Theme.defaultFont.pixelSize
                        }
                    }
                }

                // extra usage / credits
                PlasmaComponents.Label {
                    Layout.fillWidth: true
                    visible: !!section.modelData.credits
                    text: section.modelData.credits
                          ? i18n("Extra usage: $%1 / $%2",
                                 section.modelData.credits.used.toFixed(2),
                                 section.modelData.credits.cap.toFixed(0))
                          : ""
                    opacity: 0.7
                    font.pixelSize: Kirigami.Theme.defaultFont.pixelSize
                }

                // Local Claude usage (this machine)
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    spacing: 2
                    visible: section.modelData.provider_id === "claude"
                             && root.snapshot.local_claude !== null

                    PlasmaComponents.Label {
                        text: i18n("Local · this machine")
                        opacity: 0.55
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize
                    }
                    PlasmaComponents.Label {
                        text: {
                            var lc = root.snapshot.local_claude
                            if (!lc) return ""
                            return i18n("Today  %1 tok · ~$%2 equiv",
                                        full.fmtTokens(lc.today_tokens),
                                        lc.today_cost_usd.toFixed(2))
                        }
                        font.bold: true
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize
                    }
                    PlasmaComponents.Label {
                        Layout.fillWidth: true
                        text: full.splitText(root.snapshot.local_claude)
                        opacity: 0.7
                        elide: Text.ElideRight
                        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize
                    }

                    // 7-day token sparkline
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 2
                        spacing: 2
                        Repeater {
                            model: root.snapshot.local_claude ? root.snapshot.local_claude.last7days : []
                            delegate: Item {
                                id: spark
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: Kirigami.Units.gridUnit
                                Rectangle {
                                    anchors.bottom: parent.bottom
                                    width: parent.width
                                    radius: 1
                                    color: Kirigami.Theme.highlightColor
                                    opacity: 0.5
                                    height: Math.max(2, parent.height * (spark.modelData.tokens / full.maxWeekTokens()))
                                }
                            }
                        }
                    }
                }

                Kirigami.Separator { Layout.fillWidth: true; opacity: 0.5 }
            }
        }

        // push content up when short
        Item { Layout.fillWidth: true; Layout.fillHeight: true }
    }

    footer: Item {
        implicitHeight: footRow.implicitHeight + Kirigami.Units.smallSpacing * 2
        Kirigami.Separator {
            anchors { left: parent.left; right: parent.right; top: parent.top }
        }
        RowLayout {
            id: footRow
            anchors {
                fill: parent
                leftMargin: Kirigami.Units.largeSpacing
                rightMargin: Kirigami.Units.largeSpacing
                topMargin: Kirigami.Units.smallSpacing
                bottomMargin: Kirigami.Units.smallSpacing
            }
            PlasmaComponents.Label {
                Layout.fillWidth: true
                text: root.hasData
                      ? i18n("Updated %1", Qt.formatTime(root.lastUpdate, "HH:mm:ss"))
                      : i18n("Loading…")
                opacity: 0.6
                font.pixelSize: Kirigami.Theme.defaultFont.pixelSize
                elide: Text.ElideRight
            }
        }
    }

    function fmtTokens(n) {
        if (n >= 1e9) return (n / 1e9).toFixed(2) + "B"
        if (n >= 1e6) return (n / 1e6).toFixed(1) + "M"
        if (n >= 1e3) return (n / 1e3).toFixed(1) + "k"
        return "" + n
    }
    function splitText(lc) {
        if (!lc || !lc.model_split) return ""
        var parts = []
        for (var k in lc.model_split)
            parts.push(k.charAt(0).toUpperCase() + k.slice(1) + " " + Math.round(lc.model_split[k] * 100) + "%")
        return parts.join(" · ")
    }
    function maxWeekTokens() {
        var lc = root.snapshot.local_claude
        if (!lc || !lc.last7days) return 1
        var m = 1
        for (var i = 0; i < lc.last7days.length; i++) m = Math.max(m, lc.last7days[i].tokens)
        return m
    }
    function resetText(iso) {
        if (!iso) return ""
        var diff = new Date(iso).getTime() - Date.now()
        if (diff <= 0) return i18n("resetting…")
        var mins = Math.round(diff / 60000)
        if (mins < 60) return i18n("resets in %1m", mins)
        var hrs = Math.floor(mins / 60)
        if (hrs < 24) return i18n("resets in %1h %2m", hrs, mins % 60)
        var days = Math.floor(hrs / 24)
        return i18n("resets in %1d %2h", days, hrs % 24)
    }
}
