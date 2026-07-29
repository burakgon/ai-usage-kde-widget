import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.kirigami as Kirigami
import "ProviderCatalog.js" as Catalog

MouseArea {
    id: compactRoot

    readonly property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical

    implicitWidth: content.implicitWidth + Kirigami.Units.smallSpacing * 2
    implicitHeight: content.implicitHeight + Kirigami.Units.smallSpacing
    Layout.minimumWidth: vertical ? -1 : implicitWidth
    Layout.preferredWidth: implicitWidth
    Layout.maximumWidth: vertical ? Number.POSITIVE_INFINITY : implicitWidth
    Layout.preferredHeight: implicitHeight
    Layout.fillWidth: vertical
    Layout.fillHeight: !vertical

    hoverEnabled: true
    acceptedButtons: Qt.LeftButton | Qt.MiddleButton
    onClicked: (mouse) => {
        if (mouse.button === Qt.MiddleButton)
            root.refresh()
        else
            root.expanded = !root.expanded
    }

    GridLayout {
        id: content
        anchors.centerIn: parent
        columns: compactRoot.vertical ? 1 : Math.max(root.compactGroups.length, 1)
        rowSpacing: 0
        columnSpacing: Kirigami.Units.smallSpacing

        RowLayout {
            visible: root.compactGroups.length === 0
            spacing: 2

            Kirigami.Icon {
                source: "speedometer"
                Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
            }
            PlasmaComponents.Label {
                text: root.hasData ? "—" : "…"
                font.bold: true
            }
        }

        Repeater {
            model: root.compactGroups

            delegate: RowLayout {
                id: group
                required property var modelData
                spacing: 2

                Kirigami.Icon {
                    source: root.providerIconSource(group.modelData.provider_id)
                    Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                    Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                    isMask: true
                    color: Kirigami.Theme.textColor
                }

                Repeater {
                    model: group.modelData.metrics

                    delegate: RowLayout {
                        id: reading
                        required property string modelData
                        spacing: 1

                        readonly property var metric: Catalog.metric(
                            group.modelData.provider_id,
                            reading.modelData
                        )
                        readonly property var value: root.metricReading(
                            group.modelData.provider,
                            reading.modelData
                        )

                        PlasmaComponents.Label {
                            visible: group.modelData.metrics.length > 1
                            text: reading.metric ? reading.metric.short_label : ""
                            color: Kirigami.Theme.textColor
                            opacity: 0.65
                            font.pixelSize: Math.max(
                                Kirigami.Theme.smallFont.pixelSize - 1, 7
                            )
                        }
                        PlasmaComponents.Label {
                            text: root.formatReading(reading.value)
                            font.bold: true
                            color: Kirigami.Theme.textColor
                        }
                    }
                }

                Kirigami.Icon {
                    visible: group.modelData.provider
                        && group.modelData.provider.status === "stale"
                    source: "data-warning"
                    Layout.preferredWidth: Kirigami.Units.iconSizes.small
                    Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    color: Kirigami.Theme.textColor
                }
            }
        }
    }
}
