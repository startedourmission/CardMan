import Foundation
import Testing
@testable import CardManCore

private let date = Date(timeIntervalSinceReferenceDate: 0)

@Test func parsesDomesticApproval() throws {
    let text = "[Web발신]\nKB국민카드1234승인\n홍*동님\n12,000원 일시불\n11/03 14:30\n스타벅스\n누적1,234,567원"
    // 금액 다음 줄이 가맹점인 형식
    let simple = "KB국민카드 승인\n12,000원\n스타벅스\n11/03 14:30"
    let transaction = try #require(MessageParser.parse(text: simple, key: "message:1", date: date))
    #expect(transaction.amount == 12_000)
    #expect(transaction.currency == "KRW")
    #expect(transaction.merchant == "스타벅스")
    #expect(MessageParser.parse(text: text, key: "message:2", date: date)?.amount == 12_000)
}

@Test func parsesMerchantCancellation() throws {
    let text = "KB국민카드 승인\n12,000원\n스타벅스 취소\n11/03 14:30"
    let transaction = try #require(MessageParser.parse(text: text, key: "message:1", date: date))
    #expect(transaction.amount == -12_000)
    #expect(transaction.merchant == "[취소] 스타벅스")
}

@Test func parsesCancelCompleted() throws {
    let text = "[KB국민카드] 올리브영 11월03일 취소완료 (-8,500원)"
    let transaction = try #require(MessageParser.parse(text: text, key: "message:1", date: date))
    #expect(transaction.amount == -8_500)
    #expect(transaction.merchant == "[취소] 올리브영")
}

@Test func parsesForeignPayment() throws {
    let text = "KB국민카드 해외승인\n12.34(USD)\n미국 OPENAI 승인"
    let transaction = try #require(MessageParser.parse(text: text, key: "message:1", date: date))
    #expect(transaction.currency == "USD")
    #expect(transaction.originalAmount == 12.34)
    #expect(transaction.amount == 17_276)
    #expect(transaction.merchant == "미국 OPENAI")
}

@Test func ignoresMessagesWithoutAmount() {
    #expect(MessageParser.parse(text: "인증번호 123456", key: "message:1", date: date) == nil)
}

@Test func decodesTypedStreamBody() throws {
    // 실제 attributedBody의 앞부분 구조를 줄여서 만든 것
    let text = "KB국민카드 승인\n12,000원\n스타벅스\n"
    var data = Data([0x04, 0x0B]) + Data("streamtyped".utf8) + Data([0x81, 0xE8, 0x03, 0x84, 0x01, 0x40, 0x84, 0x84, 0x84])
    data += Data("NSMutableAttributedString".utf8) + Data([0x00, 0x84, 0x84])
    data += Data("NSString".utf8) + Data([0x01, 0x94, 0x84, 0x01, 0x2B])
    let bytes = Data(text.utf8)
    data += Data([0x81, UInt8(bytes.count & 0xFF), UInt8(bytes.count >> 8)]) + bytes
    data += Data([0x86, 0x84, 0x02]) + Data("iI".utf8)
    #expect(MessageParser.decodeBody(text: nil, attributedBody: data) == text)
    #expect(MessageParser.decodeBody(text: "본문", attributedBody: data) == "본문")
}

@Test func messagesTimestampUnits() {
    #expect(MessageParser.date(fromMessagesTimestamp: 1_000_000_000_000_000_000) == Date(timeIntervalSinceReferenceDate: 1_000_000_000))
    #expect(MessageParser.date(fromMessagesTimestamp: 600_000_000) == Date(timeIntervalSinceReferenceDate: 600_000_000))
}

@Test func formatsAmounts() {
    #expect(Format.won(1_234_567) == "1,234,567원")
    #expect(Format.won(-8_500) == "-8,500원")
    #expect(Format.dollars(1234.5) == "$1,234.50")
    #expect(Format.percent(0.969) == "96.9%")
}

@Test func csvEscapesFields() {
    #expect(CSVExporter.escape("스타벅스") == "스타벅스")
    #expect(CSVExporter.escape("A, B") == "\"A, B\"")
    #expect(CSVExporter.escape("say \"hi\"") == "\"say \"\"hi\"\"\"")
}

/// 실제 chat.db 복사본으로 파이썬 버전과 결과를 비교할 때만 돈다.
/// CARDMAN_PARITY_DB=<chat.db> CARDMAN_PARITY_OUT=<tsv> swift test --filter dumpForParity
@Test(.enabled(if: ProcessInfo.processInfo.environment["CARDMAN_PARITY_DB"] != nil))
func dumpForParity() throws {
    let environment = ProcessInfo.processInfo.environment
    let database = URL(fileURLWithPath: environment["CARDMAN_PARITY_DB"]!)
    let output = URL(fileURLWithPath: environment["CARDMAN_PARITY_OUT"]!)
    let sender = environment["CARDMAN_PARITY_SENDER"] ?? Settings.default.phoneNumber
    let messages = try MessagesDatabase.fetchMessages(from: sender, databaseURL: database)
    let ledger = Ledger.build(messages: messages, manual: [], exclusions: [:])
    let lines = ledger.transactions.map {
        [$0.key, Format.dateTime($0.date), String($0.amount), $0.currency, $0.merchant].joined(separator: "\t")
    }
    try (lines.joined(separator: "\n") + "\n").write(to: output, atomically: true, encoding: .utf8)
}
