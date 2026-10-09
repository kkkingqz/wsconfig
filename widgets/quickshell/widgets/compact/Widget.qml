import QtQuick
import QtQuick.Controls
Item {
    required property QtObject context
    implicitHeight: 160
    Column {
        width: parent.width; spacing: 16
        Label { text: "Компактный виджет"; color: context.foreground; font.pixelSize: 22 }
        Label { text: "Тот же framework, другой Item."; color: context.mutedForeground; width: parent.width; wrapMode: Text.WordWrap }
        Button { text: "Закрыть"; onClicked: context.requestClose() }
    }
}
