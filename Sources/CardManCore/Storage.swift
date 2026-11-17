import Foundation

/// 예산과 카드사 발신번호
public struct Settings: Codable, Equatable, Sendable {
    public var yearlyBudget: Int
    public var phoneNumber: String

    public static let `default` = Settings(yearlyBudget: 1_800_000, phoneNumber: "+8215881688")

    public init(yearlyBudget: Int, phoneNumber: String) {
        self.yearlyBudget = yearlyBudget
        self.phoneNumber = phoneNumber
    }

    enum CodingKeys: String, CodingKey {
        case yearlyBudget = "yearly_budget"
        case phoneNumber = "phone_number"
    }
}

/// 문자로 오지 않는 거래를 직접 입력한 것
public struct ManualTransaction: Codable, Identifiable, Equatable, Sendable {
    public var id: String
    /// "YYYY-MM-DD"
    public var date: String
    public var amount: Int
    public var merchant: String
    public var currency: String
    public var manual: Bool

    public init(id: String = ManualTransaction.newID(), date: String, amount: Int, merchant: String, currency: String = "KRW") {
        self.id = id
        self.date = date
        self.amount = amount
        self.merchant = merchant
        self.currency = currency
        self.manual = true
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        // 예전 파이썬 버전에서 만든 거래에는 id가 없을 수 있다.
        id = try container.decodeIfPresent(String.self, forKey: .id) ?? ""
        date = try container.decode(String.self, forKey: .date)
        amount = try container.decode(Int.self, forKey: .amount)
        merchant = try container.decode(String.self, forKey: .merchant)
        currency = try container.decodeIfPresent(String.self, forKey: .currency) ?? "KRW"
        manual = try container.decodeIfPresent(Bool.self, forKey: .manual) ?? true
    }

    public static func newID() -> String {
        UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
    }

    public var transactionKey: String { "manual:\(id)" }
}

/// 설정과 수동 거래, 예산 제외 목록을 홈 폴더의 JSON 파일에 저장한다.
/// 파일 이름과 형식은 예전 파이썬 버전과 같아서 그대로 이어서 쓸 수 있다.
public struct Storage: Sendable {
    public let settingsURL: URL
    public let manualTransactionsURL: URL
    public let excludedTransactionsURL: URL

    public init(home: URL = FileManager.default.homeDirectoryForCurrentUser) {
        settingsURL = home.appendingPathComponent(".cardman_config.json")
        manualTransactionsURL = home.appendingPathComponent(".cardman_manual_transactions.json")
        excludedTransactionsURL = home.appendingPathComponent(".cardman_excluded_transactions.json")
    }

    public func loadSettings() -> Settings {
        (try? read(Settings.self, from: settingsURL)) ?? .default
    }

    public func saveSettings(_ settings: Settings) throws {
        try write(settings, to: settingsURL)
    }

    public func loadManualTransactions() -> [ManualTransaction] {
        guard var transactions = try? read([ManualTransaction].self, from: manualTransactionsURL) else {
            return []
        }
        // id가 없던 거래에 영구 id를 붙여 둬야 예산 제외 상태가 같은 거래에 계속 붙어 있다.
        var changed = false
        for index in transactions.indices where transactions[index].id.isEmpty {
            transactions[index].id = ManualTransaction.newID()
            changed = true
        }
        if changed {
            try? saveManualTransactions(transactions)
        }
        return transactions
    }

    public func saveManualTransactions(_ transactions: [ManualTransaction]) throws {
        try write(transactions, to: manualTransactionsURL)
    }

    /// 예산 제외 목록. 예전 형식(전액 제외 키 배열)도 읽는다.
    public func loadExclusions() -> [String: Exclusion] {
        if let file = try? read(ExclusionsFile.self, from: excludedTransactionsURL) {
            var exclusions = Dictionary(uniqueKeysWithValues: file.full.map { ($0, Exclusion.full) })
            for (key, amount) in file.partial where amount > 0 {
                exclusions[key] = .partial(amount)
            }
            return exclusions
        }
        let keys = (try? read([String].self, from: excludedTransactionsURL)) ?? []
        return Dictionary(keys.map { ($0, Exclusion.full) }, uniquingKeysWith: { first, _ in first })
    }

    public func saveExclusions(_ exclusions: [String: Exclusion]) throws {
        var file = ExclusionsFile(full: [], partial: [:])
        for (key, exclusion) in exclusions {
            switch exclusion {
            case .full: file.full.append(key)
            case .partial(let amount): file.partial[key] = amount
            }
        }
        file.full.sort()
        try write(file, to: excludedTransactionsURL)
    }

    /// {"full": ["message:1"], "partial": {"message:2": 5000}}
    private struct ExclusionsFile: Codable {
        var full: [String]
        var partial: [String: Int]
    }

    private func read<T: Decodable>(_ type: T.Type, from url: URL) throws -> T {
        try JSONDecoder().decode(type, from: Data(contentsOf: url))
    }

    private func write<T: Encodable>(_ value: T, to url: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        try encoder.encode(value).write(to: url, options: .atomic)
    }
}
