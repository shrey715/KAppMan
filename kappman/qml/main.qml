import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root
    title: "KAppMan – AppImage Manager"
    width: 560
    height: 480
    minimumWidth: 480
    minimumHeight: 400

    pageStack.initialPage: Kirigami.ScrollablePage {
        title: "AppImage Manager"

        Kirigami.FormLayout {
            anchors.fill: parent

            // Watch directory
            Controls.TextField {
                id: watchDirField
                Kirigami.FormData.label: "Watch Directory:"
                placeholderText: "~/AppImages"
                text: "~/AppImages"
            }
            Controls.Button {
                text: "Browse…"
                onClicked: folderDialog.open()
            }

            Kirigami.Separator { Kirigami.FormData.isSection: true; Kirigami.FormData.label: "Actions" }

            Controls.Button {
                text: "⚡ Integrate All"
                onClicked: console.log("Integrating all from", watchDirField.text)
            }

            Controls.Button {
                text: "👁 Start Watcher"
                checkable: true
                onToggled: console.log(checked ? "Watcher started" : "Watcher stopped")
            }
        }
    }
}
