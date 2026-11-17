import AppKit
import SwiftUI

@main
struct CardManApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    private let model = AppModel.shared

    static let mainWindowID = "main"

    var body: some Scene {
        Window("카드맨", id: Self.mainWindowID) {
            MainWindowView(model: model)
        }
        .defaultSize(width: 960, height: 780)
        .windowResizability(.contentMinSize)

        MenuBarExtra {
            MenuBarMenu(model: model)
        } label: {
            MenuBarLabel(model: model)
        }
        .menuBarExtraStyle(.menu)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        MainActor.assumeIsolated {
            AppModel.shared.start()
        }
    }

    /// 응용 프로그램 폴더에서 카드맨을 다시 누르면 상세 창을 연다.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        MainActor.assumeIsolated {
            AppModel.shared.openMainWindow?()
        }
        return true
    }

    /// 창을 닫아도 메뉴바에는 남는다.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }
}

/// 메뉴바 글자. 앱이 떠 있는 동안 항상 살아 있어서 창 여는 동작을 여기서 모델에 넘겨 둔다.
struct MenuBarLabel: View {
    let model: AppModel
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Text(model.menuBarTitle)
            .onAppear {
                model.openMainWindow = {
                    openWindow(id: CardManApp.mainWindowID)
                    NSApp.activate()
                }
            }
    }
}
