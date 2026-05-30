import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    property var local: null   // {today_tokens, today_cost_usd, model_split, last7days}
    visible: local !== null
    Layout.fillWidth: true
    radius: 7; color: "#222629"
    implicitHeight: col.implicitHeight + 16

    function fmtTokens(n) {
        if (n >= 1e6) return (n / 1e6).toFixed(2) + "M"
        if (n >= 1e3) return (n / 1e3).toFixed(1) + "k"
        return "" + n
    }
    function splitText() {
        if (!local || !local.model_split) return ""
        var parts = []
        for (var k in local.model_split)
            parts.push(k.charAt(0).toUpperCase() + k.slice(1) + " "
                       + Math.round(local.model_split[k] * 100) + "%")
        return parts.join(" · ")
    }

    ColumnLayout {
        id: col
        anchors.fill: parent; anchors.margins: 8; spacing: 4
        Text { text: "LOCAL · THIS MACHINE"; color: "#717a80"
               font.pointSize: 8.5; font.letterSpacing: 0.5 }
        RowLayout {
            Layout.fillWidth: true
            Text { text: "Today"; color: "#bdc3c7"; font.pixelSize: 11 }
            Item { Layout.fillWidth: true }
            Text { text: root.local ? root.fmtTokens(root.local.today_tokens)
                         + " tok   ~$" + root.local.today_cost_usd.toFixed(2) : ""
                   color: "#fcfcfc"; font.pixelSize: 11; font.bold: true }
        }
        Text { text: root.splitText(); color: "#7f8c8d"; font.pixelSize: 10 }
        RowLayout {
            Layout.fillWidth: true; spacing: 2; Layout.topMargin: 4
            Repeater {
                model: root.local ? root.local.last7days : []
                Rectangle {
                    Layout.fillWidth: true
                    height: 20
                    color: "transparent"
                    Rectangle {
                        anchors.bottom: parent.bottom; width: parent.width; radius: 1
                        color: "#3a6c86"
                        property real maxTok: {
                            var m = 1
                            var d = root.local ? root.local.last7days : []
                            for (var i = 0; i < d.length; i++) m = Math.max(m, d[i].tokens)
                            return m
                        }
                        height: Math.max(2, 20 * (modelData.tokens / maxTok))
                    }
                }
            }
        }
    }
}
