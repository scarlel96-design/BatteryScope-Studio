import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    visible: true
    width: 960
    height: 640
    minimumWidth: 700
    minimumHeight: 480
    title: "BatteryScope Studio"
    color: "#121820"

    Shortcut {
        sequence: "Ctrl+Shift+X"
        onActivated: backend.emergencyStop()
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 32
        spacing: 20

        Label {
            text: "BatteryScope Studio"
            color: "#f1f5f9"
            font.pixelSize: 30
            font.bold: true
        }
        Label {
            text: "Devices"
            color: "#94a3b8"
            font.pixelSize: 18
        }
        Label {
            text: "Virtual C2  ·  Available\nVirtual EBD  ·  Available"
            color: "#f1f5f9"
            font.pixelSize: 18
            lineHeight: 1.7
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: "#334155"
        }
        Label {
            text: backend.status
            color: "#f1f5f9"
            font.pixelSize: 20
        }
        Item { Layout.fillHeight: true }
        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Button {
                text: "Start Simulation"
                onClicked: backend.startSimulation()
            }
            Item { Layout.fillWidth: true }
            Button {
                text: "Emergency Stop"
                onClicked: backend.emergencyStop()
            }
        }
    }
}
