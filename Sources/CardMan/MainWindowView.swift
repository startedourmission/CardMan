import AppKit
import CardManCore
import SwiftUI

extension Color {
    /// 강조색은 이 파랑 하나만 쓴다.
    static let cardManAccent = Color(red: 0x31 / 255, green: 0x82 / 255, blue: 0xF6 / 255)
}

/// 상세 창
struct MainWindowView: View {
    let model: AppModel

    @State private var tab: Tab = .transactions
    @State private var budgetText = ""
    @State private var phoneText = ""
    @State private var showingAddSheet = false
    @State private var showingManageSheet = false

    enum Tab: Hashable, CaseIterable {
        case transactions
        case period(Period)

        static let allCases: [Tab] = [.transactions] + Period.allCases.map(Tab.period)

        var title: String {
            switch self {
            case .transactions: "거래 내역"
            case .period(.daily): "일별 집계"
            case .period(.monthly): "월별 집계"
            case .period(.quarterly): "분기별 집계"
            case .period(.yearly): "연도별 집계"
            }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            if model.accessDenied {
                AccessBanner(model: model)
                    .padding(.top, 16)
            }
            BudgetSection(summary: model.summary)
                .padding(.top, 22)
            StatsRow(summary: model.summary)
                .padding(.top, 24)
            Divider()
                .padding(.top, 24)
                .padding(.bottom, 8)
            tabBar
            tabContent
                .frame(maxHeight: .infinity)
            Divider()
            bottomBar
                .padding(.top, 14)
            Text(model.status)
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .padding(.top, 10)
        }
        .padding(EdgeInsets(top: 22, leading: 28, bottom: 16, trailing: 28))
        .frame(minWidth: 820, minHeight: 640)
        .tint(.cardManAccent)
        .sheet(isPresented: $showingAddSheet) {
            AddManualTransactionSheet(model: model)
        }
        .sheet(isPresented: $showingManageSheet) {
            ManageManualTransactionsSheet(model: model)
        }
        .onAppear {
            budgetText = String(model.settings.yearlyBudget)
            phoneText = model.settings.phoneNumber
            // 창이 떠 있는 동안만 Dock에 아이콘을 보인다.
            NSApp.setActivationPolicy(.regular)
            NSApp.activate()
            Task { await model.refresh() }
        }
        .onDisappear {
            NSApp.setActivationPolicy(.accessory)
        }
    }

    private var header: some View {
        HStack {
            Text("카드맨")
                .font(.system(size: 17, weight: .bold))
            Spacer()
            Button {
                Task { await model.refresh() }
            } label: {
                Text(model.isLoading ? "불러오는 중" : "새로고침")
                    .frame(minWidth: 64)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(model.isLoading)
            .keyboardShortcut("r")
        }
    }

    private var tabBar: some View {
        HStack(spacing: 22) {
            ForEach(Tab.allCases, id: \.self) { item in
                Button {
                    tab = item
                } label: {
                    Text(item.title)
                        .font(.system(size: 13, weight: tab == item ? .bold : .regular))
                        .foregroundStyle(tab == item ? .primary : .secondary)
                        .padding(.vertical, 6)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.bottom, 4)
    }

    @ViewBuilder
    private var tabContent: some View {
        switch tab {
        case .transactions:
            TransactionsTable(model: model)
        case .period(let period):
            PeriodTable(period: period, rows: model.ledger?.rows(for: period) ?? [])
        }
    }

    private var bottomBar: some View {
        HStack(spacing: 8) {
            Text("연간 예산")
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
            TextField("", text: $budgetText)
                .frame(width: 110)
                .onSubmit(applySettings)
            Text("전화번호")
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .padding(.leading, 10)
            TextField("", text: $phoneText)
                .frame(width: 140)
                .onSubmit(applySettings)
            Spacer()
            Button("수동 추가") { showingAddSheet = true }
            Button("수동 거래 관리") { showingManageSheet = true }
            Button("CSV 내보내기") { model.exportCSV() }
                .disabled(model.ledger == nil)
        }
        .textFieldStyle(.roundedBorder)
    }

    private func applySettings() {
        model.updateSettings(budgetText: budgetText, phoneNumber: phoneText)
        budgetText = String(model.settings.yearlyBudget)
    }
}

/// 권한이 없을 때 위에 뜨는 안내
private struct AccessBanner: View {
    let model: AppModel

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("메시지를 읽으려면 전체 디스크 접근 권한이 필요합니다")
                    .font(.system(size: 13, weight: .semibold))
                Text("시스템 설정 › 개인정보 보호 및 보안 › 전체 디스크 접근 권한에서 카드맨을 켠 뒤 새로고침하세요.")
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("설정 열기") { model.openFullDiskAccessSettings() }
        }
        .padding(14)
        .background(Color.cardManAccent.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
    }
}

/// 큰 숫자는 예산 사용률 하나만
private struct BudgetSection: View {
    let summary: BudgetSummary?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("\(String(summary?.year ?? Calendar.current.component(.year, from: Date())))년 예산 사용")
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
            HStack(alignment: .lastTextBaseline) {
                Text(summary?.ratio.map { Format.percent($0) } ?? "-")
                    .font(.system(size: 34, weight: .bold))
                    .monospacedDigit()
                Spacer()
                Text(remainingText)
                    .font(.system(size: 13))
            }
            ProgressBar(ratio: summary?.ratio ?? 0)
                .padding(.top, 4)
                .padding(.bottom, 8)
            Text(totalText)
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
        }
    }

    private var remainingText: String {
        guard let summary else { return "" }
        let remaining = summary.remaining
        return remaining >= 0 ? "\(Format.won(remaining)) 남음" : "\(Format.won(-remaining)) 초과"
    }

    private var totalText: String {
        guard let summary else { return "" }
        var text = "\(Format.won(summary.total)) 사용 · 예산 \(Format.won(summary.budget))"
        if summary.excludedCount > 0 {
            text += " · 예산 제외 \(summary.excludedCount)건 (\(Format.won(summary.excludedAmount)))"
        }
        return text
    }
}

private struct ProgressBar: View {
    let ratio: Double

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule().fill(Color.secondary.opacity(0.15))
                if ratio > 0 {
                    Capsule()
                        .fill(Color.cardManAccent)
                        .frame(width: max(6, proxy.size.width * min(ratio, 1)))
                }
            }
        }
        .frame(height: 6)
    }
}

/// 보조 수치: 박스 없이 한 줄
private struct StatsRow: View {
    let summary: BudgetSummary?

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            stat("이번 달", summary.map { Format.won($0.thisMonth) })
            stat("월평균", summary.map { Format.won($0.averageMonthly) })
            stat("원화 결제", summary.map { Format.won($0.krw) })
            stat("달러 결제", summary.map { Format.dollars($0.usd) })
        }
    }

    private func stat(_ caption: String, _ value: String?) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(caption)
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
            Text(value ?? "-")
                .font(.system(size: 15))
                .monospacedDigit()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// 거래 내역 표. 최신 거래가 위에 온다.
private struct TransactionsTable: View {
    let model: AppModel
    @State private var selection: String?

    private struct Row: Identifiable {
        let number: Int
        let transaction: CardManCore.Transaction
        var id: String { transaction.key }
    }

    var body: some View {
        let transactions = model.ledger?.transactions ?? []
        let rows = transactions.enumerated().reversed().map { Row(number: $0.offset + 1, transaction: $0.element) }

        Table(rows, selection: $selection) {
            TableColumn("번호") { row in
                Text("\(row.number)")
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            .width(56)
            TableColumn("날짜") { row in
                Text(Format.dateTime(row.transaction.date))
                    .monospacedDigit()
                    .foregroundStyle(style(row))
            }
            .width(150)
            TableColumn("금액") { row in
                Text(Format.won(row.transaction.amount))
                    .monospacedDigit()
                    .foregroundStyle(style(row))
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
            .width(120)
            TableColumn("가맹점") { row in
                Text(row.transaction.merchant)
                    .foregroundStyle(style(row))
            }
            TableColumn("예산 제외") { row in
                ExclusionCell(model: model, transaction: row.transaction, isSelected: selection == row.id)
            }
            .width(150)
        }
        // 선택한 거래를 스페이스바로 전액 제외하거나 다시 넣는다.
        .onKeyPress(.space) {
            guard let selection, let row = rows.first(where: { $0.id == selection }) else { return .ignored }
            let excluded = model.exclusion(for: row.transaction) != nil
            model.setExclusion(excluded ? nil : .full, for: row.transaction)
            return .handled
        }
    }

    private func style(_ row: Row) -> HierarchicalShapeStyle {
        model.exclusion(for: row.transaction) == .full ? .tertiary : .primary
    }
}

/// 체크하면 전액 제외. "일부"를 누르면 뺄 금액을 직접 넣는다.
private struct ExclusionCell: View {
    let model: AppModel
    let transaction: CardManCore.Transaction
    let isSelected: Bool
    @State private var editing = false
    /// 선택된 줄이 파란 배경으로 강조되면 .increased
    @Environment(\.backgroundProminence) private var prominence

    /// 파란 선택 배경 위에서는 흰색, 그 밖에는 강조색
    private var linkColor: Color {
        prominence == .increased ? .white : .cardManAccent
    }

    var body: some View {
        let exclusion = model.exclusion(for: transaction)
        HStack(spacing: 8) {
            Toggle("예산 제외", isOn: Binding(
                get: { exclusion == .full },
                set: { model.setExclusion($0 ? .full : nil, for: transaction) }
            ))
            .toggleStyle(.checkbox)
            .labelsHidden()

            if case .partial(let amount) = exclusion {
                Button("−\(Format.won(amount))") { editing = true }
                    .buttonStyle(.plain)
                    .foregroundStyle(linkColor)
                    .monospacedDigit()
                    .help("일부 제외 금액 바꾸기")
            } else if isSelected && exclusion == nil {
                Button("일부만 제외") { editing = true }
                    .buttonStyle(.plain)
                    .foregroundStyle(linkColor)
            }
            Spacer(minLength: 0)
        }
        .popover(isPresented: $editing, arrowEdge: .bottom) {
            PartialExclusionEditor(model: model, transaction: transaction)
        }
    }
}

/// 거래 금액 중 예산에서 뺄 만큼만 입력한다.
private struct PartialExclusionEditor: View {
    let model: AppModel
    let transaction: CardManCore.Transaction
    @Environment(\.dismiss) private var dismiss
    @State private var amountText = ""
    @FocusState private var focused: Bool

    private var total: Int { abs(transaction.amount) }
    private var amount: Int? { Int(amountText.filter(\.isNumber)) }
    private var isValid: Bool { amount.map { $0 > 0 && $0 <= total } ?? false }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("예산에서 뺄 금액")
                .font(.system(size: 13, weight: .semibold))
            Text("\(transaction.merchant) · 결제 \(Format.won(transaction.amount))")
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
            HStack {
                TextField("금액", text: $amountText)
                    .textFieldStyle(.roundedBorder)
                    .frame(width: 140)
                    .focused($focused)
                    .onSubmit(apply)
                Text("원")
            }
            Text(hint)
                .font(.system(size: 12))
                .foregroundStyle(isValid || amountText.isEmpty ? .secondary : Color.red)
            HStack {
                if model.exclusion(for: transaction) != nil {
                    Button("제외 취소") {
                        model.setExclusion(nil, for: transaction)
                        dismiss()
                    }
                }
                Spacer()
                Button("적용", action: apply)
                    .buttonStyle(.borderedProminent)
                    .disabled(!isValid)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(16)
        .frame(width: 280)
        .tint(.cardManAccent)
        .onAppear {
            if case .partial(let current) = model.exclusion(for: transaction) {
                amountText = String(current)
            }
            focused = true
        }
    }

    private var hint: String {
        guard let amount else { return "결제 금액 중 예산에 넣지 않을 금액을 입력하세요" }
        guard amount > 0, amount <= total else { return "0원보다 크고 \(Format.won(total)) 이하로 입력하세요" }
        return "예산에는 \(Format.won(total - amount))만 들어갑니다"
    }

    private func apply() {
        guard isValid, let amount else { return }
        model.setExclusion(.partial(amount), for: transaction)
        dismiss()
    }
}

/// 일별·월별·분기별·연도별 집계표
private struct PeriodTable: View {
    let period: Period
    let rows: [PeriodRow]

    private struct Row: Identifiable {
        let number: Int
        let row: PeriodRow
        var id: String { row.id }
    }

    var body: some View {
        let numbered = rows.enumerated().map { Row(number: $0.offset + 1, row: $0.element) }
        Table(numbered) {
            TableColumn("번호") { item in
                Text("\(item.number)")
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            .width(56)
            TableColumn(period.columnTitle) { item in
                Text(item.row.label).monospacedDigit()
            }
            TableColumn("금액") { item in
                amount(Format.won(item.row.amount))
            }
            TableColumn("건수") { item in
                amount(Format.number(item.row.count))
            }
            TableColumn("누적금액") { item in
                amount(Format.won(item.row.cumulative))
            }
        }
    }

    private func amount(_ text: String) -> some View {
        Text(text)
            .monospacedDigit()
            .frame(maxWidth: .infinity, alignment: .trailing)
    }
}
