import Foundation

/// 거래 내역과 기간별 집계를 엑셀에서 바로 열리는 CSV(UTF-8 BOM)로 저장한다.
public enum CSVExporter {
    public static let transactionsFileName = "transactions.csv"

    /// 저장한 파일 이름들을 돌려준다.
    @discardableResult
    public static func export(_ ledger: Ledger, to folder: URL) throws -> [String] {
        var files: [(String, [[String]])] = []

        let transactionRows = ledger.transactions.map { transaction in
            let excluded = switch ledger.exclusion(for: transaction) {
            case nil: "아니오"
            case .full: "예"
            case .partial: "일부"
            }
            return [
                Format.dateTime(transaction.date),
                String(transaction.amount),
                transaction.merchant,
                excluded,
                String(ledger.excludedAmount(transaction)),
            ]
        }
        files.append((transactionsFileName, [["날짜", "금액", "가맹점", "예산 제외", "제외 금액"]] + transactionRows))

        for period in Period.allCases {
            let rows = ledger.rows(for: period).map {
                [$0.label, String($0.amount), String($0.count), String($0.cumulative)]
            }
            files.append((period.csvFileName, [[period.columnTitle, "금액", "건수", "누적금액"]] + rows))
        }

        for (name, rows) in files {
            let body = rows.map { $0.map(escape).joined(separator: ",") }.joined(separator: "\n") + "\n"
            try Data(("\u{FEFF}" + body).utf8).write(to: folder.appendingPathComponent(name), options: .atomic)
        }
        return files.map(\.0)
    }

    static func escape(_ field: String) -> String {
        guard field.contains(where: { $0 == "," || $0 == "\"" || $0 == "\n" || $0 == "\r" }) else {
            return field
        }
        return "\"" + field.replacingOccurrences(of: "\"", with: "\"\"") + "\""
    }
}
