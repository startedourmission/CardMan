import AppKit
import CardManCore
import SwiftUI

/// 메뉴바 아이콘을 누르면 나오는 메뉴
struct MenuBarMenu: View {
    let model: AppModel

    var body: some View {
        Button("카드맨 열기") { model.openMainWindow?() }
        Divider()
        Button("통계 새로고침") { Task { await model.refresh() } }
            .disabled(model.isLoading)
        Button("접근 권한 설정") { model.openFullDiskAccessSettings() }
        Divider()

        if model.accessDenied {
            info("메시지 접근 권한 필요")
            info("설정에서 전체 디스크 접근을 허용한 뒤 새로고침하세요")
        } else if let summary = model.summary {
            info("올해 총: \(Format.won(summary.total)) / \(Format.won(summary.budget))")
            info("한도: \(progressBar(summary.ratio ?? 0))")
            info("잔여: \(Format.won(summary.remaining))")
            info("달러: \(Format.dollars(summary.usd))")
        } else {
            info(model.status)
        }

        if !model.recentTransactions.isEmpty {
            Divider()
            info("최근 거래 내역")
            ForEach(model.recentTransactions) { transaction in
                let marker = switch model.exclusion(for: transaction) {
                case nil: ""
                case .full: "⊘ "
                case .partial: "◐ "
                }
                info("\(marker)\(Format.shortDateTime(transaction.date)) | \(Format.won(transaction.amount)) | \(transaction.merchant.prefix(20))")
            }
        }

        Divider()
        Button("종료") { NSApp.terminate(nil) }
            .keyboardShortcut("q")
    }

    /// 눌러도 아무 일 없는 정보 줄. 비활성 회색 글씨가 되지 않도록 버튼으로 둔다.
    private func info(_ text: String) -> some View {
        Button(text) {}
    }

    /// "████████░░ 80%"
    private func progressBar(_ ratio: Double) -> String {
        let length = 10
        let filled = max(0, min(length, Int(ratio * Double(length))))
        let bar = String(repeating: "█", count: filled) + String(repeating: "░", count: length - filled)
        return "\(bar) \(Format.percent(ratio, fractionDigits: 0))"
    }
}
