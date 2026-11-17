import Foundation

/// 카드 결제 한 건. 금액은 항상 원화로 환산한 값이다.
public struct Transaction: Identifiable, Hashable, Sendable {
    /// 예산 제외 목록에 저장하는 영구 식별자. 문자는 "message:<ROWID>", 수동 거래는 "manual:<id>".
    public let key: String
    public let date: Date
    public let amount: Int
    public let currency: String
    /// 해외 결제의 원래 금액 (예: 12.34 USD). 원화 결제와 수동 거래는 nil.
    public let originalAmount: Double?
    public let merchant: String

    public var id: String { key }

    public init(
        key: String,
        date: Date,
        amount: Int,
        currency: String,
        originalAmount: Double? = nil,
        merchant: String
    ) {
        self.key = key
        self.date = date
        self.amount = amount
        self.currency = currency
        self.originalAmount = originalAmount
        self.merchant = merchant
    }
}

/// 메시지 DB에서 읽은 문자 한 통
public struct RawMessage: Sendable {
    public let rowID: Int64
    /// 2001-01-01부터의 나노초 (오래된 DB는 초)
    public let date: Int64
    public let text: String?
    public let attributedBody: Data?

    public init(rowID: Int64, date: Int64, text: String?, attributedBody: Data?) {
        self.rowID = rowID
        self.date = date
        self.text = text
        self.attributedBody = attributedBody
    }
}
