import Foundation

public enum Format {
    private static let grouped: NumberFormatter = {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.numberStyle = .decimal
        formatter.usesGroupingSeparator = true
        formatter.groupingSeparator = ","
        formatter.groupingSize = 3
        formatter.maximumFractionDigits = 0
        return formatter
    }()

    /// 12000 → "12,000"
    public static func number(_ value: Int) -> String {
        grouped.string(from: NSNumber(value: value)) ?? String(value)
    }

    /// 12000 → "12,000원"
    public static func won(_ value: Int) -> String {
        "\(number(value))원"
    }

    /// 소수 금액은 반올림해서 원으로
    public static func won(_ value: Double) -> String {
        won(Int(value.rounded()))
    }

    /// 1234.5 → "$1,234.50"
    public static func dollars(_ value: Double) -> String {
        let cents = Int((value * 100).rounded())
        return String(format: "$%@.%02d", number(cents / 100), abs(cents % 100))
    }

    /// 0.969 → "96.9%"
    public static func percent(_ ratio: Double, fractionDigits: Int = 1) -> String {
        String(format: "%.\(fractionDigits)f%%", ratio * 100)
    }

    /// 거래 목록 날짜 "2026-11-03 14:30"
    public static func dateTime(_ date: Date) -> String {
        date.formatted(.verbatim(
            "\(year: .defaultDigits)-\(month: .twoDigits)-\(day: .twoDigits) \(hour: .twoDigits(clock: .twentyFourHour, hourCycle: .zeroBased)):\(minute: .twoDigits)",
            timeZone: .current,
            calendar: .current
        ))
    }

    /// 메뉴바 최근 거래 날짜 "11/03 14:30"
    public static func shortDateTime(_ date: Date) -> String {
        date.formatted(.verbatim(
            "\(month: .twoDigits)/\(day: .twoDigits) \(hour: .twoDigits(clock: .twentyFourHour, hourCycle: .zeroBased)):\(minute: .twoDigits)",
            timeZone: .current,
            calendar: .current
        ))
    }
}
