import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: root
    modal: true
    width: 260
    padding: 14
    anchors.centerIn: Overlay.overlay
    visible: true

    ColumnLayout {
        anchors.fill: parent; spacing: 10
        Label { text: "Settings"; font.bold: true }
        RowLayout {
            Layout.fillWidth: true
            Label { text: "Refresh (s)"; Layout.fillWidth: true }
            SpinBox { from: 180; to: 3600; stepSize: 60
                      value: controller.refreshSeconds
                      onValueModified: controller.setRefreshSeconds(value) }
        }
        CheckBox { text: "Show % badge on tray icon"
                   checked: controller.badgeEnabled
                   onToggled: controller.setBadgeEnabled(checked) }
        CheckBox { text: "Start automatically on login"
                   checked: controller.autostartEnabled
                   onToggled: controller.setAutostart(checked) }
    }
}
