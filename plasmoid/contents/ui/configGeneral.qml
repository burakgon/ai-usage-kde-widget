import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.FormLayout {
    id: page

    property string cfg_badgeWindow: "session"
    property alias cfg_refreshInterval: refreshSpin.value

    QQC2.ComboBox {
        id: badgeCombo
        Kirigami.FormData.label: i18n("Panel badge shows:")
        textRole: "text"
        valueRole: "value"
        model: [
            { value: "session", text: i18n("Session usage (5-hour)") },
            { value: "weekly",  text: i18n("Weekly usage (7-day)") }
        ]
        Component.onCompleted: currentIndex = indexOfValue(page.cfg_badgeWindow)
        onActivated: page.cfg_badgeWindow = currentValue
    }

    Item { Kirigami.FormData.isSection: true }

    QQC2.SpinBox {
        id: refreshSpin
        Kirigami.FormData.label: i18n("Refresh every (seconds):")
        from: 60
        to: 3600
        stepSize: 30
    }
}
