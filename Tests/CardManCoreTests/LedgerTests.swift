import Foundation
import Testing
@testable import CardManCore

private var calendar: Calendar {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(identifier: "Asia/Seoul")!
    return calendar
}

private func day(_ month: Int, _ day: Int) -> Date {
    calendar.date(from: DateComponents(year: 2026, month: month, day: day, hour: 12))!
}

private let transactions = [
    Transaction(key: "message:1", date: day(1, 5), amount: 10_000, currency: "KRW", merchant: "A"),
    Transaction(key: "message:2", date: day(1, 20), amount: 30_000, currency: "KRW", merchant: "B"),
    Transaction(key: "message:3", date: day(2, 1), amount: 14_000, currency: "USD", originalAmount: 10, merchant: "C"),
    Transaction(key: "message:4", date: day(2, 3), amount: -5_000, currency: "KRW", merchant: "[취소] D"),
]

@Test func partialExclusionReducesBudgetAmount() {
    let ledger = Ledger(
        transactions: transactions,
        exclusions: ["message:1": .full, "message:2": .partial(12_000), "message:3": .partial(7_000)],
        calendar: calendar
    )
    let summary = ledger.summary(budget: 100_000, now: day(2, 10))
    // 0 + 18,000 + 7,000 - 5,000
    #expect(summary.total == 20_000)
    #expect(summary.krw == 13_000)
    #expect(summary.usd == 5)
    #expect(summary.thisMonth == 2_000)
    #expect(summary.excludedCount == 3)
    #expect(summary.excludedAmount == 29_000)

    let monthly = ledger.rows(for: .monthly)
    #expect(monthly == [
        PeriodRow(label: "2026-01", amount: 18_000, count: 1, cumulative: 18_000),
        PeriodRow(label: "2026-02", amount: 2_000, count: 2, cumulative: 20_000),
    ])
}

@Test func partialExclusionOnRefundKeepsSign() {
    let ledger = Ledger(transactions: transactions, exclusions: ["message:4": .partial(2_000)], calendar: calendar)
    #expect(ledger.excludedAmount(transactions[3]) == -2_000)
    #expect(ledger.budgetAmount(transactions[3]) == -3_000)
}

@Test func readsLegacyAndNewExclusionFiles() throws {
    let home = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: home) }
    let storage = Storage(home: home)

    // 파이썬 버전 형식: 전액 제외 키 배열
    try Data(#"["message:1", "message:2"]"#.utf8).write(to: storage.excludedTransactionsURL)
    #expect(storage.loadExclusions() == ["message:1": .full, "message:2": .full])

    try storage.saveExclusions(["message:1": .full, "manual:abc": .partial(5_000)])
    #expect(storage.loadExclusions() == ["message:1": .full, "manual:abc": .partial(5_000)])
}
