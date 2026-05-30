import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    property string caption: ""
    property real percent: 0
    property string color: "#3daee9"
    property string resetText: ""
    spacing: 2
    Layout.fillWidth: true

    RowLayout {
        Layout.fillWidth: true
        Text { text: root.caption; color: "#bdc3c7"; font.pixelSize: 11 }
        Item { Layout.fillWidth: true }
        Text { text: Math.round(root.percent) + "%"; color: root.color
               font.pixelSize: 11; font.bold: true }
    }
    Rectangle {
        Layout.fillWidth: true; height: 6; radius: 3; color: "#45494d"
        Rectangle {
            width: parent.width * Math.min(1, root.percent / 100)
            height: parent.height; radius: 3; color: root.color
            Behavior on width { NumberAnimation { duration: 250 } }
        }
    }
    Text {
        visible: root.resetText.length > 0
        text: root.resetText; color: "#7f8c8d"; font.pixelSize: 9
    }
}
