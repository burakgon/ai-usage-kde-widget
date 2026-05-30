import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.kirigami as Kirigami

MouseArea {
    id: compactRoot

    readonly property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical

    implicitWidth: layout.implicitWidth + Kirigami.Units.smallSpacing * 2
    implicitHeight: layout.implicitHeight

    Layout.minimumWidth: vertical ? -1 : implicitWidth
    Layout.preferredWidth: implicitWidth
    Layout.maximumWidth: vertical ? Number.POSITIVE_INFINITY : implicitWidth
    Layout.preferredHeight: implicitHeight
    Layout.fillWidth: vertical
    Layout.fillHeight: !vertical

    hoverEnabled: true
    acceptedButtons: Qt.LeftButton | Qt.MiddleButton
    onClicked: (mouse) => {
        if (mouse.button === Qt.MiddleButton) root.refresh()
        else root.expanded = !root.expanded
    }

    RowLayout {
        id: layout
        anchors.centerIn: parent
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Icon {
            source: "speedometer"
            Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
            Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
            Layout.alignment: Qt.AlignVCenter
            opacity: 0.9
        }

        PlasmaComponents.Label {
            Layout.alignment: Qt.AlignVCenter
            text: root.hasData ? root.badgeValue + "%" : "…"
            font.bold: true
            color: Kirigami.Theme.textColor
        }
    }
}
