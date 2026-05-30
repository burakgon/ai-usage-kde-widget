import QtQuick
import QtQuick.Layouts

ColumnLayout {
    id: root
    property var provider: ({})
    property var local: null      // only for claude
    spacing: 6
    Layout.fillWidth: true

    RowLayout {
        Layout.fillWidth: true; spacing: 8
        Rectangle {
            width: 22; height: 22; radius: 6
            color: root.provider.provider_id === "claude" ? "#d97757" : "#10a37f"
            Text { anchors.centerIn: parent
                   text: root.provider.provider_id === "claude" ? "C" : "O"
                   color: "white"; font.bold: true; font.pixelSize: 12 }
        }
        Text { text: root.provider.display_name || ""; color: "#fcfcfc"
               font.pixelSize: 13; font.bold: true }
        Item { Layout.fillWidth: true }
        Rectangle {
            visible: !!root.provider.plan
            radius: 9; color: "#3a3f44"
            implicitWidth: planText.implicitWidth + 14
            implicitHeight: planText.implicitHeight + 5
            Text { id: planText; anchors.centerIn: parent; text: root.provider.plan || ""
                   color: "#cfd6dc"; font.pixelSize: 9 }
        }
    }

    Text {
        visible: root.provider.status !== undefined && root.provider.status !== "ok"
        text: root.provider.error_message || ""
        color: "#f67400"; font.pixelSize: 10; Layout.fillWidth: true; wrapMode: Text.WordWrap
    }

    Repeater {
        model: root.provider.windows || []
        UsageBar {
            caption: modelData.caption
            percent: modelData.used_percent
            color: modelData.color
            resetText: {
                var t = modelData.resets_at ? "resets " + Qt.formatDateTime(
                          new Date(modelData.resets_at), "ddd hh:mm") : ""
                if (root.provider.credits && modelData.kind === "weekly")
                    t += (t ? " · " : "") + "extra $" + root.provider.credits.used.toFixed(2)
                         + (root.provider.credits.cap > 0 ? " / $" + root.provider.credits.cap : "")
                return t
            }
        }
    }

    LocalBlock { local: root.local }
}
