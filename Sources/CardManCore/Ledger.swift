import Foundation

/// 집계 단위
public enum Period: String, CaseIterable, Identifiable, Sendable {
    case daily, monthly, quarterly, yearly

    public var id: String { rawValue }

    /// 표 첫 열 이름 (CSV 머리글로도 쓴다)
    public var columnTitle: String {
        switch self {
        case .daily: "날짜"
        case .monthly: "월"
        case .quarterly: "분기"
        case .yearly: "연도"
        }
    }

    public var csvFileName: String { "\(rawValue).csv" }
}

/// 집계표 한 줄
public struct PeriodRow: Identifiable, Equatable, Sendable {
    /// "2026-01-05", "2026-01", "2026Q1", "2026"
    public let label: String
    public let amount: Int
    public let count: Int
    public let cumulative: Int

    public var id: String { label }
}

/// 거래를 예산 합계에서 얼마나 뺄지
public enum Exclusion: Equatable, Sendable {
    /// 전액 제외
    case full
    /// 이 금액만 제외 (양수, 거래 금액보다 작다)
    case partial(Int)
}

/// 올해 예산 요약 (예산 제외 금액은 빠진 값)
public struct BudgetSummary: Equatable, Sendable {
    public let year: Int
    public let budget: Int
    public let total: Int
    public let krw: Int
    public let usd: Double
    public let thisMonth: Int
    public let averageMonthly: Double
    /// 올해 전액 또는 일부를 제외한 거래 수
    public let excludedCount: Int
    /// 올해 예산에서 뺀 금액 합계
    public let excludedAmount: Int

    /// 예산 대비 사용 비율 (1.0 = 100%). 예산이 0 이하면 nil.
    public var ratio: Double? { budget > 0 ? Double(total) / Double(budget) : nil }
    public var remaining: Int { budget - total }
}

/// 문자와 수동 거래를 합친 전체 거래 목록과 그 집계
public struct Ledger: Sendable {
    /// 오래된 순
    public let transactions: [Transaction]
    public let exclusions: [String: Exclusion]
    public let calendar: Calendar

    public init(transactions: [Transaction], exclusions: [String: Exclusion], calendar: Calendar = .current) {
        self.transactions = transactions
        self.exclusions = exclusions
        self.calendar = calendar
    }

    /// 문자와 수동 거래를 합쳐 날짜순으로 정렬한다. 날짜가 같으면 들어온 순서를 지킨다.
    public static func build(
        messages: [RawMessage],
        manual: [ManualTransaction],
        exclusions: [String: Exclusion],
        calendar: Calendar = .current
    ) -> Ledger {
        var transactions = messages.compactMap(MessageParser.parse)
        transactions += manual.compactMap { item in
            guard let date = parseManualDate(item.date, calendar: calendar) else { return nil }
            return Transaction(
                key: item.transactionKey, date: date, amount: item.amount,
                currency: item.currency, merchant: "[수동] \(item.merchant)"
            )
        }
        let sorted = transactions.enumerated()
            .sorted { ($0.element.date, $0.offset) < ($1.element.date, $1.offset) }
            .map(\.element)
        return Ledger(transactions: sorted, exclusions: exclusions, calendar: calendar)
    }

    public func exclusion(for transaction: Transaction) -> Exclusion? {
        exclusions[transaction.key]
    }

    /// 예산에서 뺀 금액. 취소(음수) 거래는 같은 부호로 뺀다.
    public func excludedAmount(_ transaction: Transaction) -> Int {
        switch exclusion(for: transaction) {
        case nil:
            return 0
        case .full:
            return transaction.amount
        case .partial(let amount):
            let magnitude = min(amount, abs(transaction.amount))
            return transaction.amount < 0 ? -magnitude : magnitude
        }
    }

    /// 예산 합계에 들어가는 금액
    public func budgetAmount(_ transaction: Transaction) -> Int {
        transaction.amount - excludedAmount(transaction)
    }

    /// 예산에 조금이라도 들어가는 거래 (전액 제외한 거래만 빠진다)
    public var included: [Transaction] {
        transactions.filter { exclusion(for: $0) != .full }
    }

    public func rows(for period: Period) -> [PeriodRow] {
        var order: [String] = []
        var totals: [String: (amount: Int, count: Int)] = [:]
        for transaction in included {
            let label = label(for: transaction.date, period: period)
            if totals[label] == nil {
                order.append(label)
            }
            totals[label, default: (0, 0)].amount += budgetAmount(transaction)
            totals[label, default: (0, 0)].count += 1
        }
        // 라벨은 0을 채운 숫자라 문자열 순서가 곧 시간 순서다.
        var cumulative = 0
        return order.sorted().map { label in
            let value = totals[label]!
            cumulative += value.amount
            return PeriodRow(label: label, amount: value.amount, count: value.count, cumulative: cumulative)
        }
    }

    public func summary(budget: Int, now: Date = Date()) -> BudgetSummary {
        let year = calendar.component(.year, from: now)
        let month = calendar.component(.month, from: now)
        let thisYear = included.filter { calendar.component(.year, from: $0.date) == year }

        let total = thisYear.reduce(0) { $0 + budgetAmount($1) }
        let krw = thisYear.filter { $0.currency == "KRW" }.reduce(0) { $0 + budgetAmount($1) }
        // 해외 결제를 일부만 뺐으면 원래 금액도 같은 비율로 줄인다.
        let usd = thisYear.filter { $0.currency == "USD" }.reduce(0.0) { sum, transaction in
            guard let original = transaction.originalAmount, transaction.amount != 0 else { return sum }
            return sum + original * Double(budgetAmount(transaction)) / Double(transaction.amount)
        }
        let thisMonth = thisYear
            .filter { calendar.component(.month, from: $0.date) == month }
            .reduce(0) { $0 + budgetAmount($1) }
        let months = Set(thisYear.map { calendar.component(.month, from: $0.date) }).count
        let excludedThisYear = transactions.filter {
            exclusion(for: $0) != nil && calendar.component(.year, from: $0.date) == year
        }

        return BudgetSummary(
            year: year,
            budget: budget,
            total: total,
            krw: krw,
            usd: usd,
            thisMonth: thisMonth,
            averageMonthly: months > 0 ? Double(total) / Double(months) : 0,
            excludedCount: excludedThisYear.count,
            excludedAmount: excludedThisYear.reduce(0) { $0 + excludedAmount($1) }
        )
    }

    private func label(for date: Date, period: Period) -> String {
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        let year = parts.year!, month = parts.month!, day = parts.day!
        switch period {
        case .daily: return String(format: "%04d-%02d-%02d", year, month, day)
        case .monthly: return String(format: "%04d-%02d", year, month)
        case .quarterly: return String(format: "%04dQ%d", year, (month - 1) / 3 + 1)
        case .yearly: return String(year)
        }
    }

    /// 수동 거래 날짜 "YYYY-MM-DD" (시간이 붙어 있어도 받는다)
    static func parseManualDate(_ text: String, calendar: Calendar) -> Date? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = calendar
        formatter.timeZone = calendar.timeZone
        for format in ["yyyy-MM-dd", "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd'T'HH:mm:ss"] {
            formatter.dateFormat = format
            if let date = formatter.date(from: text) {
                return date
            }
        }
        return nil
    }
}
