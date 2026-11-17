import AppKit
import CardManCore
import Observation

/// 메뉴바와 상세 창이 함께 보는 상태
@MainActor
@Observable
final class AppModel {
    static let shared = AppModel()

    /// 전체 디스크 접근 권한 설정 화면
    static let fullDiskAccessURL = URL(
        string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
    )!

    /// 메뉴바 숫자가 너무 오래되지 않도록 주기적으로 다시 읽는다.
    private static let autoRefreshInterval: Duration = .seconds(30 * 60)

    private let storage = Storage()

    private(set) var settings: Settings
    private(set) var ledger: Ledger?
    private(set) var manualTransactions: [ManualTransaction] = []
    private(set) var isLoading = false
    private(set) var accessDenied = false
    private(set) var status = "메시지를 불러오는 중..."

    /// 상세 창을 여는 동작. 항상 살아 있는 메뉴바 라벨이 채워 둔다.
    var openMainWindow: (() -> Void)?

    private var exclusions: [String: Exclusion]
    private var started = false

    private init() {
        settings = storage.loadSettings()
        exclusions = storage.loadExclusions()
        manualTransactions = storage.loadManualTransactions()
    }

    var summary: BudgetSummary? {
        ledger?.summary(budget: settings.yearlyBudget)
    }

    /// 메뉴바에 보이는 글자
    var menuBarTitle: String {
        if accessDenied { return "⚠️" }
        guard let ratio = summary?.ratio else { return "카드맨" }
        let percent = Format.percent(ratio, fractionDigits: 0)
        return ratio > 1 ? "⚠️ \(percent)" : "₩ \(percent)"
    }

    /// 최근 거래 5건, 최신순
    var recentTransactions: [Transaction] {
        Array((ledger?.transactions ?? []).suffix(5).reversed())
    }

    func exclusion(for transaction: Transaction) -> Exclusion? {
        exclusions[transaction.key]
    }

    /// 앱이 뜰 때 한 번 부른다.
    func start() {
        guard !started else { return }
        started = true
        Task {
            while !Task.isCancelled {
                await refresh()
                try? await Task.sleep(for: Self.autoRefreshInterval)
            }
        }
    }

    func refresh() async {
        guard !isLoading else { return }
        let phoneNumber = settings.phoneNumber.trimmingCharacters(in: .whitespaces)
        guard !phoneNumber.isEmpty else {
            status = "전화번호를 입력해주세요"
            return
        }

        isLoading = true
        status = "메시지를 불러오는 중..."
        defer { isLoading = false }

        manualTransactions = storage.loadManualTransactions()
        exclusions = storage.loadExclusions()
        let manual = manualTransactions
        let currentExclusions = exclusions

        do {
            let ledger = try await Task.detached(priority: .userInitiated) {
                let messages = try MessagesDatabase.fetchMessages(from: phoneNumber)
                return Ledger.build(messages: messages, manual: manual, exclusions: currentExclusions)
            }.value
            self.ledger = ledger
            accessDenied = false
            if ledger.transactions.isEmpty {
                status = "금액 정보가 있는 메시지를 찾지 못했습니다. 전화번호를 확인해주세요"
            } else {
                let excludedCount = ledger.transactions.count { ledger.exclusion(for: $0) != nil }
                status = "총 \(ledger.transactions.count)건 · 예산 제외 \(excludedCount)건 · "
                    + "\(Date().formatted(date: .omitted, time: .shortened)) 업데이트"
            }
        } catch MessagesDatabaseError.accessDenied {
            accessDenied = true
            status = "메시지 접근 권한이 필요합니다"
        } catch {
            status = error.localizedDescription
        }
    }

    // MARK: - 설정

    /// 예산이나 전화번호를 바꾸면 저장하고 다시 읽는다.
    func updateSettings(budgetText: String, phoneNumber: String) {
        let digits = budgetText.filter(\.isNumber)
        guard let budget = Int(digits), budget > 0 else {
            status = "연간 예산을 숫자로 입력해주세요"
            return
        }
        let updated = Settings(yearlyBudget: budget, phoneNumber: phoneNumber.trimmingCharacters(in: .whitespaces))
        let senderChanged = updated.phoneNumber != settings.phoneNumber
        settings = updated
        save { try storage.saveSettings(updated) }
        if senderChanged || ledger == nil {
            Task { await refresh() }
        }
    }

    // MARK: - 예산 제외

    /// nil이면 예산에 다시 전부 넣는다. 거래 금액 이상을 일부 제외로 넣으면 전액 제외로 본다.
    func setExclusion(_ exclusion: Exclusion?, for transaction: Transaction) {
        var normalized = exclusion
        if case .partial(let amount) = exclusion {
            if amount <= 0 {
                normalized = nil
            } else if amount >= abs(transaction.amount) {
                normalized = .full
            }
        }

        var updated = exclusions
        updated[transaction.key] = normalized
        guard save({ try storage.saveExclusions(updated) }) else { return }
        exclusions = updated
        if let ledger {
            self.ledger = Ledger(transactions: ledger.transactions, exclusions: updated, calendar: ledger.calendar)
        }
        status = switch normalized {
        case nil: "\(transaction.merchant) 거래를 예산 합계에 다시 넣었습니다"
        case .full: "\(transaction.merchant) 거래를 예산 합계에서 뺐습니다"
        case .partial(let amount): "\(transaction.merchant) 거래에서 \(Format.won(amount))만 예산 합계에서 뺐습니다"
        }
    }

    // MARK: - 수동 거래

    func addManualTransaction(_ transaction: ManualTransaction) {
        var transactions = storage.loadManualTransactions()
        transactions.append(transaction)
        guard save({ try storage.saveManualTransactions(transactions) }) else { return }
        manualTransactions = transactions
        Task { await refresh() }
    }

    func deleteManualTransaction(id: String) {
        var transactions = storage.loadManualTransactions()
        transactions.removeAll { $0.id == id }
        guard save({ try storage.saveManualTransactions(transactions) }) else { return }
        manualTransactions = transactions
        Task { await refresh() }
    }

    // MARK: - CSV

    func exportCSV() {
        guard let ledger else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.prompt = "여기에 저장"
        panel.message = "CSV 파일을 저장할 폴더를 고르세요"
        panel.directoryURL = FileManager.default.urls(for: .desktopDirectory, in: .userDomainMask).first
        guard panel.runModal() == .OK, let folder = panel.url else { return }
        do {
            let files = try CSVExporter.export(ledger, to: folder)
            status = "CSV \(files.count)개 저장 완료: \(folder.path)"
            NSWorkspace.shared.activateFileViewerSelecting([folder.appendingPathComponent(CSVExporter.transactionsFileName)])
        } catch {
            status = "CSV 저장 실패: \(error.localizedDescription)"
        }
    }

    // MARK: - 기타

    func openFullDiskAccessSettings() {
        NSWorkspace.shared.open(Self.fullDiskAccessURL)
    }

    @discardableResult
    private func save(_ body: () throws -> Void) -> Bool {
        do {
            try body()
            return true
        } catch {
            status = "저장 실패: \(error.localizedDescription)"
            return false
        }
    }
}
