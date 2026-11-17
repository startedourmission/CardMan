import CardManCore
import SwiftUI

/// 문자로 오지 않는 거래(현금 결제 등)를 직접 넣는다.
struct AddManualTransactionSheet: View {
    let model: AppModel
    @Environment(\.dismiss) private var dismiss

    @State private var date = Date()
    @State private var amountText = ""
    @State private var merchant = ""
    @State private var currency = "KRW"
    @State private var error: String?

    private static let currencies = ["KRW", "USD", "EUR", "JPY"]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("거래 수동 추가")
                .font(.system(size: 15, weight: .bold))
            Form {
                DatePicker("날짜", selection: $date, displayedComponents: .date)
                TextField("금액 (원)", text: $amountText)
                TextField("가맹점", text: $merchant)
                Picker("통화", selection: $currency) {
                    ForEach(Self.currencies, id: \.self) { Text($0) }
                }
            }
            .textFieldStyle(.roundedBorder)
            if let error {
                Text(error)
                    .font(.system(size: 12))
                    .foregroundStyle(.red)
            }
            HStack {
                Spacer()
                Button("취소", role: .cancel) { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Button("추가", action: save)
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 380)
    }

    private func save() {
        guard let amount = Int(amountText.replacingOccurrences(of: ",", with: "").trimmed) else {
            error = "금액을 숫자로 입력해주세요"
            return
        }
        let name = merchant.trimmed
        guard !name.isEmpty else {
            error = "가맹점명을 입력해주세요"
            return
        }
        let day = date.formatted(.iso8601.year().month().day().dateSeparator(.dash))
        model.addManualTransaction(ManualTransaction(date: day, amount: amount, merchant: name, currency: currency))
        dismiss()
    }
}

/// 수동 거래 목록과 삭제
struct ManageManualTransactionsSheet: View {
    let model: AppModel
    @Environment(\.dismiss) private var dismiss

    @State private var selection: String?
    @State private var pendingDelete: ManualTransaction?

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("수동 거래 관리")
                .font(.system(size: 15, weight: .bold))
            List(model.manualTransactions, selection: $selection) { item in
                HStack {
                    Text(String(item.date.prefix(10)))
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                    Text(item.merchant)
                    Spacer()
                    Text(Format.won(item.amount))
                        .monospacedDigit()
                }
                .tag(item.id)
            }
            .overlay {
                if model.manualTransactions.isEmpty {
                    Text("직접 추가한 거래가 없습니다")
                        .foregroundStyle(.secondary)
                }
            }
            HStack {
                Spacer()
                Button("삭제") {
                    pendingDelete = model.manualTransactions.first { $0.id == selection }
                }
                .disabled(selection == nil)
                Button("닫기") { dismiss() }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(20)
        .frame(width: 560, height: 420)
        .confirmationDialog(
            "\(pendingDelete?.merchant ?? "") 거래를 삭제할까요?",
            isPresented: Binding(get: { pendingDelete != nil }, set: { if !$0 { pendingDelete = nil } })
        ) {
            Button("삭제", role: .destructive) {
                if let pendingDelete {
                    model.deleteManualTransaction(id: pendingDelete.id)
                }
                selection = nil
            }
        }
    }
}

private extension String {
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }
}
