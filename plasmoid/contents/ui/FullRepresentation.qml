import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.extras as PlasmaExtras
import org.kde.kirigami as Kirigami

PlasmaExtras.Representation {
    id: full

    Layout.minimumWidth: Kirigami.Units.gridUnit * 18
    Layout.minimumHeight: Kirigami.Units.gridUnit * 15
    Layout.preferredWidth: Kirigami.Units.gridUnit * 23
    Layout.preferredHeight: Kirigami.Units.gridUnit * 28

    header: PlasmaExtras.PlasmoidHeading {
        ColumnLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing

            RowLayout {
                Layout.fillWidth: true

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

            RowLayout {
                Layout.fillWidth: true

                PlasmaComponents.Label {
                    Layout.fillWidth: true
                    text: i18n("Show")
                    opacity: 0.65
                }
                QQC2.Button {
                    text: i18n("Left")
                    checkable: true
                    checked: root.usageMode === "remaining"
                    onClicked: root.setUsageMode("remaining")
                }
                QQC2.Button {
                    text: i18n("Used")
                    checkable: true
                    checked: root.usageMode === "used"
                    onClicked: root.setUsageMode("used")
                }
            }
        }
    }

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        Kirigami.InlineMessage {
            Layout.fillWidth: true
            visible: root.updateInfo && root.updateInfo.update_available
            type: Kirigami.MessageType.Information
            text: root.updateInfo
                ? i18n("AI Usage %1 is available.", root.updateInfo.latest_version)
                : ""
            actions: [
                Kirigami.Action {
                    text: i18n("View update")
                    icon.name: "software-update-available"
                    onTriggered: root.openUpdate()
                }
            ]
        }

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

        PlasmaExtras.PlaceholderMessage {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.hasData
                && (root.snapshot.installed_provider_ids || []).length === 0
            iconName: "system-search"
            text: i18n("No supported tools detected")
            explanation: i18n(
                "Install or sign in to a supported AI coding tool, then refresh."
            )
        }

        PlasmaExtras.PlaceholderMessage {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.hasData
                && (root.snapshot.installed_provider_ids || []).length > 0
                && (root.snapshot.providers || []).length === 0
            iconName: "view-hidden"
            text: i18n("No tracked providers")
            explanation: i18n("Choose providers in the widget settings.")
        }

        QQC2.ScrollView {
            id: providerScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.hasData && (root.snapshot.providers || []).length > 0
            contentWidth: availableWidth
            QQC2.ScrollBar.horizontal.policy: QQC2.ScrollBar.AlwaysOff
            QQC2.ScrollBar.vertical.policy: (root.snapshot.providers || []).length > 2
                ? QQC2.ScrollBar.AsNeeded : QQC2.ScrollBar.AlwaysOff

            ColumnLayout {
                width: providerScroll.availableWidth
                spacing: Kirigami.Units.largeSpacing

                Repeater {
                    model: root.snapshot.providers || []

                    delegate: ColumnLayout {
                        id: providerSection
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.smallSpacing

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            Kirigami.Icon {
                                source: root.providerIconSource(
                                    providerSection.modelData.provider_id
                                )
                                Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                                Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                                isMask: true
                                color: Kirigami.Theme.textColor
                            }
                            Kirigami.Heading {
                                Layout.fillWidth: true
                                level: 3
                                text: providerSection.modelData.display_name
                                elide: Text.ElideRight
                            }
                            PlasmaComponents.Label {
                                visible: !!providerSection.modelData.plan
                                text: providerSection.modelData.plan || ""
                                opacity: 0.65
                                elide: Text.ElideRight
                            }
                            Kirigami.Icon {
                                visible: providerSection.modelData.status === "stale"
                                source: "data-warning"
                                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                Layout.preferredHeight: Kirigami.Units.iconSizes.small
                                color: Kirigami.Theme.neutralTextColor
                            }
                        }

                        Kirigami.InlineMessage {
                            Layout.fillWidth: true
                            visible: providerSection.modelData.status !== "ok"
                            type: providerSection.modelData.status === "stale"
                                || providerSection.modelData.status === "rate_limited"
                                ? Kirigami.MessageType.Warning
                                : Kirigami.MessageType.Error
                            text: full.failureText(providerSection.modelData)
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 2
                            columnSpacing: Kirigami.Units.smallSpacing
                            rowSpacing: Kirigami.Units.smallSpacing

                            Repeater {
                                model: providerSection.modelData.windows || []

                                delegate: Rectangle {
                                    id: quotaCard
                                    required property var modelData
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: (
                                        providerScroll.availableWidth
                                        - Kirigami.Units.smallSpacing
                                    ) / 2
                                    implicitHeight: quotaContent.implicitHeight
                                        + Kirigami.Units.largeSpacing * 2
                                    radius: Kirigami.Units.smallSpacing
                                    color: Qt.rgba(
                                        Kirigami.Theme.textColor.r,
                                        Kirigami.Theme.textColor.g,
                                        Kirigami.Theme.textColor.b,
                                        0.055
                                    )

                                    ColumnLayout {
                                        id: quotaContent
                                        anchors {
                                            left: parent.left
                                            right: parent.right
                                            top: parent.top
                                            margins: Kirigami.Units.largeSpacing
                                        }
                                        spacing: Kirigami.Units.smallSpacing

                                        RowLayout {
                                            Layout.fillWidth: true
                                            PlasmaComponents.Label {
                                                Layout.fillWidth: true
                                                text: quotaCard.modelData.caption
                                                opacity: 0.72
                                                elide: Text.ElideRight
                                            }
                                            PlasmaComponents.Label {
                                                text: Math.round(root.displayedPercent(
                                                    Number(quotaCard.modelData.used_percent)
                                                )) + "%"
                                                font.bold: true
                                                color: root.valueColor(
                                                    Number(quotaCard.modelData.used_percent)
                                                )
                                            }
                                        }

                                        Rectangle {
                                            Layout.fillWidth: true
                                            height: Math.round(Kirigami.Units.gridUnit * 0.35)
                                            radius: height / 2
                                            color: Qt.rgba(
                                                Kirigami.Theme.textColor.r,
                                                Kirigami.Theme.textColor.g,
                                                Kirigami.Theme.textColor.b,
                                                0.14
                                            )

                                            Rectangle {
                                                width: parent.width * Math.max(
                                                    0,
                                                    Math.min(
                                                        1,
                                                        root.displayedPercent(
                                                            Number(
                                                                quotaCard.modelData.used_percent
                                                            )
                                                        ) / 100
                                                    )
                                                )
                                                height: parent.height
                                                radius: height / 2
                                                color: root.barColor(
                                                    Number(quotaCard.modelData.used_percent)
                                                )
                                                Behavior on width {
                                                    NumberAnimation {
                                                        duration: 250
                                                        easing.type: Easing.OutCubic
                                                    }
                                                }
                                            }
                                        }

                                        PlasmaComponents.Label {
                                            visible: !!quotaCard.modelData.resets_at
                                            text: full.relativeReset(
                                                quotaCard.modelData.resets_at
                                            )
                                            opacity: 0.55
                                            font: Kirigami.Theme.smallFont
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                id: billingCard
                                visible: !!providerSection.modelData.billing_usage
                                Layout.fillWidth: true
                                Layout.preferredWidth: (
                                    providerScroll.availableWidth
                                    - Kirigami.Units.smallSpacing
                                ) / 2
                                implicitHeight: billingColumn.implicitHeight
                                    + Kirigami.Units.largeSpacing * 2
                                radius: Kirigami.Units.smallSpacing
                                color: Qt.rgba(
                                    Kirigami.Theme.textColor.r,
                                    Kirigami.Theme.textColor.g,
                                    Kirigami.Theme.textColor.b,
                                    0.055
                                )

                                ColumnLayout {
                                    id: billingColumn
                                    anchors {
                                        left: parent.left
                                        right: parent.right
                                        top: parent.top
                                        margins: Kirigami.Units.largeSpacing
                                    }
                                    PlasmaComponents.Label {
                                        text: full.billingTitle(
                                            providerSection.modelData.billing_usage
                                        )
                                        opacity: 0.72
                                    }
                                    PlasmaComponents.Label {
                                        text: full.billingValue(
                                            providerSection.modelData.billing_usage
                                        )
                                        font.bold: true
                                    }
                                }
                            }
                        }

                        Kirigami.Separator {
                            Layout.fillWidth: true
                            opacity: 0.45
                        }
                    }
                }
            }
        }
    }

    footer: Item {
        implicitHeight: footerRow.implicitHeight + Kirigami.Units.smallSpacing * 2

        Kirigami.Separator {
            anchors {
                left: parent.left
                right: parent.right
                top: parent.top
            }
        }
        RowLayout {
            id: footerRow
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
                font: Kirigami.Theme.smallFont
                elide: Text.ElideRight
            }
            PlasmaComponents.Label {
                text: root.usageMode === "used" ? i18n("Used") : i18n("Left")
                opacity: 0.6
                font: Kirigami.Theme.smallFont
            }
        }
    }

    function failureText(providerData) {
        var text = providerData.error_message || providerData.status
        if (providerData.status === "stale")
            text = i18n("Showing the last successful reading. %1", text)
        if (providerData.retry_at)
            text += " " + relativeRetry(providerData.retry_at)
        return text
    }

    function relativeReset(iso) {
        if (!iso)
            return ""
        var difference = new Date(iso).getTime() - Date.now()
        if (difference <= 0)
            return i18n("Resetting…")
        var minutes = Math.max(1, Math.round(difference / 60000))
        if (minutes < 60)
            return i18np("Resets in %1 minute", "Resets in %1 minutes", minutes)
        var hours = Math.floor(minutes / 60)
        if (hours < 24)
            return i18n("Resets in %1h %2m", hours, minutes % 60)
        var days = Math.floor(hours / 24)
        return i18n("Resets in %1d %2h", days, hours % 24)
    }

    function relativeRetry(iso) {
        var difference = new Date(iso).getTime() - Date.now()
        if (difference <= 0)
            return i18n("Ready to retry.")
        var minutes = Math.max(1, Math.ceil(difference / 60000))
        if (minutes < 60)
            return i18np("Retry in %1 minute.", "Retry in %1 minutes.", minutes)
        return i18n("Retry in %1h %2m.", Math.floor(minutes / 60), minutes % 60)
    }

    function billingTitle(billing) {
        return billing && billing.kind === "flex_credit_balance"
            ? i18n("Credits") : i18n("Extra Usage")
    }

    function billingValue(billing) {
        if (!billing)
            return ""
        if (billing.kind === "bounded_spend") {
            var used = Number(billing.used_amount || 0)
            var limit = Number(billing.limit_amount || 0)
            var value = root.usageMode === "used" ? used : Math.max(limit - used, 0)
            return "$" + value.toFixed(2)
                + (root.usageMode === "used" ? " / $" + limit.toFixed(2) : "")
        }
        if (billing.kind === "unbounded_spend")
            return "$" + Number(billing.used_amount || 0).toFixed(2)
        if (billing.kind === "flex_credit_balance")
            return i18n(
                "%1 (~$%2)",
                billing.remaining_credits,
                Number(billing.usd_value || 0).toFixed(2)
            )
        return ""
    }
}
