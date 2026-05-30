import QtQuick
import QtQuick.Layouts
import QtQuick.Window

Window {
    id: win
    width: 300
    height: content.implicitHeight + 24
    flags: Qt.Popup | Qt.FramelessWindowHint
    color: "#2a2e32"

    property var snapshot: ({ providers: [], local_claude: null })
    function reload() {
        try { snapshot = JSON.parse(controller.snapshotJson) }
        catch (e) { snapshot = ({ providers: [], local_claude: null }) }
    }
    Connections { target: controller; function onSnapshotChanged() { win.reload() } }
    Component.onCompleted: reload()

    Rectangle {
        anchors.fill: parent; color: "transparent"
        border.color: "#15181a"; radius: 11
        ColumnLayout {
            id: content
            anchors.fill: parent; anchors.margins: 12; spacing: 10

            RowLayout {
                Layout.fillWidth: true
                Text { text: "AI Usage"; color: "#fcfcfc"; font.pixelSize: 13; font.bold: true }
                Item { Layout.fillWidth: true }
                Text { text: "⟳"; color: "#7f8c8d"; font.pixelSize: 14
                       MouseArea { anchors.fill: parent; onClicked: controller.refresh_async() } }
                Text { text: "⚙"; color: "#7f8c8d"; font.pixelSize: 14
                       MouseArea { anchors.fill: parent; onClicked: settingsLoader.toggle() } }
            }

            Repeater {
                model: win.snapshot.providers
                ProviderSection {
                    provider: modelData
                    local: modelData.provider_id === "claude" ? win.snapshot.local_claude : null
                    Layout.fillWidth: true
                }
            }
        }
    }

    Loader {
        id: settingsLoader
        function toggle() { source = source == "" ? "Settings.qml" : "" }
    }
}
