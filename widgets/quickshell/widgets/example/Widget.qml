import QtQuick
import QtQuick.Controls
Item {
    required property QtObject context
    implicitHeight: 420
    Column {
        width: parent.width; spacing: 20
        Label { text: "Workstation widgets"; color: "#eef1f8"; font.pixelSize: 24; font.bold: true }
        Label { text: "Общий контейнер • отдельное содержимое"; color: "#aeb9d0"; width: parent.width; wrapMode: Text.WordWrap }
        Label { text: "Размер содержимого: " + context.contentWidth + " × " + context.contentHeight + "\nМасштаб Qt: " + context.devicePixelRatio + "\nСостояние: " + context.phase; color: "#eef1f8" }
        Button { text: "Закрыть"; onClicked: context.requestClose() }
    }
}
