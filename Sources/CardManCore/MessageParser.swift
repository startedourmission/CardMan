import Foundation

/// 카드사 문자 본문에서 거래를 뽑아낸다.
public enum MessageParser {
    /// 해외 결제 환산용 대략적인 환율
    public static let exchangeRates: [String: Double] = [
        "KRW": 1, "USD": 1400, "EUR": 1400, "JPY": 9, "CNY": 180, "GBP": 1650,
    ]

    private static let cancelPattern = regex(#"취소완료\s+\(-?([\d,]+)원\)"#)
    private static let cancelMerchantPattern = regex(#"\]\s+(.+?)\s+\d+월\d+일"#)
    private static let wonPattern = regex(#"([\d,]+)원"#)
    private static let wonMerchantPattern = regex(#"([\d,]+)원\n(.+?)\n"#)
    private static let foreignPattern = regex(#"([\d,]+\.?\d*)\((KRW|USD|EUR|JPY|CNY|GBP)\)"#)
    private static let foreignMerchantPattern = regex(#"(미국|일본|중국|영국|프랑스|독일|캐나다|호주)\s+(.+?)\s+승인"#)

    /// 문자 한 통을 거래로 바꾼다. 금액이 없는 문자는 nil.
    public static func parse(_ message: RawMessage) -> Transaction? {
        let text = decodeBody(text: message.text, attributedBody: message.attributedBody)
        return parse(text: text, key: "message:\(message.rowID)", date: date(fromMessagesTimestamp: message.date))
    }

    public static func parse(text: String, key: String, date: Date) -> Transaction? {
        // 취소 내역: "취소완료 (-12,000원)"
        if let match = firstMatch(cancelPattern, in: text), let amount = parseWon(match[1]) {
            let merchant = firstMatch(cancelMerchantPattern, in: text)?[1].trimmed ?? "[취소]"
            return Transaction(key: key, date: date, amount: -amount, currency: "KRW", merchant: "[취소] \(merchant)")
        }

        // 원화 결제: 금액 다음 줄이 가맹점
        if let match = firstMatch(wonPattern, in: text), var amount = parseWon(match[1]) {
            var merchant = firstMatch(wonMerchantPattern, in: text)?[2].trimmed ?? ""
            if merchant.hasSuffix("취소") {
                amount = -amount
                merchant = "[취소] \(merchant.dropLast(2).trimmed)"
            }
            return Transaction(key: key, date: date, amount: amount, currency: "KRW", merchant: merchant)
        }

        // 해외 결제: "12.34(USD)"
        if let match = firstMatch(foreignPattern, in: text),
           let original = Double(match[1].replacingOccurrences(of: ",", with: "")) {
            let currency = match[2]
            let merchant = firstMatch(foreignMerchantPattern, in: text).map { "\($0[1]) \($0[2])" } ?? ""
            let amount = Int(original * (exchangeRates[currency] ?? 1))
            return Transaction(
                key: key, date: date, amount: amount, currency: currency,
                originalAmount: original, merchant: merchant
            )
        }
        return nil
    }

    /// 메시지 DB의 date 값을 Date로. 최근 DB는 나노초, 오래된 DB는 초 단위다.
    public static func date(fromMessagesTimestamp value: Int64) -> Date {
        let seconds = value > 10_000_000_000 ? Double(value) / 1_000_000_000 : Double(value)
        return Date(timeIntervalSinceReferenceDate: seconds)
    }

    /// text 칸이 비어 있으면 attributedBody(typedstream으로 저장된 NSAttributedString)에서 본문을 꺼낸다.
    public static func decodeBody(text: String?, attributedBody: Data?) -> String {
        if let text, !text.isEmpty {
            return text
        }
        guard let attributedBody else { return "" }
        return typedStreamString(attributedBody) ?? ""
    }

    /// typedstream 안의 첫 NSString 내용을 읽는다.
    /// 구조: "NSString" 클래스명 → 몇 바이트 → '+' → 길이 → UTF-8 바이트.
    /// 길이는 0x81이면 뒤 2바이트, 0x82면 뒤 4바이트(리틀 엔디언), 그 밖에는 그 바이트 값이다.
    static func typedStreamString(_ data: Data) -> String? {
        let bytes = [UInt8](data)
        let marker = Array("NSString".utf8)
        guard let markerStart = bytes.firstRange(of: marker)?.lowerBound else { return nil }
        var index = markerStart + marker.count
        let searchEnd = min(index + 8, bytes.count)
        guard let plus = bytes[index..<searchEnd].firstIndex(of: 0x2B) else { return nil }
        index = plus + 1
        guard index < bytes.count else { return nil }

        let length: Int
        switch bytes[index] {
        case 0x81:
            guard index + 2 < bytes.count else { return nil }
            length = Int(bytes[index + 1]) | Int(bytes[index + 2]) << 8
            index += 3
        case 0x82:
            guard index + 4 < bytes.count else { return nil }
            length = (0..<4).reduce(0) { $0 | Int(bytes[index + 1 + $1]) << (8 * $1) }
            index += 5
        default:
            length = Int(bytes[index])
            index += 1
        }
        guard length > 0, index + length <= bytes.count else { return nil }
        return String(decoding: bytes[index..<(index + length)], as: UTF8.self)
    }

    // MARK: - 정규식

    private static func regex(_ pattern: String) -> NSRegularExpression {
        // 패턴은 고정 문자열이라 실패하면 코드 버그다.
        try! NSRegularExpression(pattern: pattern)
    }

    /// 첫 매치의 전체와 그룹들. 매치되지 않은 그룹은 빈 문자열.
    private static func firstMatch(_ regex: NSRegularExpression, in text: String) -> [String]? {
        let range = NSRange(text.startIndex..., in: text)
        guard let match = regex.firstMatch(in: text, range: range) else { return nil }
        return (0..<match.numberOfRanges).map { group in
            Range(match.range(at: group), in: text).map { String(text[$0]) } ?? ""
        }
    }

    /// "12,000" → 12000. 숫자가 없으면 nil.
    private static func parseWon(_ text: String) -> Int? {
        Int(text.replacingOccurrences(of: ",", with: ""))
    }
}

extension StringProtocol {
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }
}
