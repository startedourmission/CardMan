import Foundation
import SQLite3

public enum MessagesDatabaseError: Error, LocalizedError {
    /// 전체 디스크 접근 권한이 없어 chat.db를 읽지 못함
    case accessDenied
    case sqlite(String)

    public var errorDescription: String? {
        switch self {
        case .accessDenied:
            return "메시지 데이터베이스를 읽을 수 없습니다. 전체 디스크 접근 권한을 확인하세요."
        case .sqlite(let message):
            return "메시지 데이터베이스 오류: \(message)"
        }
    }
}

/// macOS 메시지 앱의 chat.db를 읽는다.
public enum MessagesDatabase {
    public static let defaultURL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Messages/chat.db")

    /// 발신번호가 sender인 문자를 오래된 순으로 읽는다.
    ///
    /// 메시지 앱이 쓰는 중인 DB를 직접 열지 않고, WAL 파일까지 임시 폴더에 매번 새로 복사해서 연다.
    /// 복사본은 읽고 나서 바로 지운다.
    public static func fetchMessages(from sender: String, databaseURL: URL = defaultURL) throws -> [RawMessage] {
        let fileManager = FileManager.default
        let workDir = fileManager.temporaryDirectory
            .appendingPathComponent("CardMan-\(UUID().uuidString)", isDirectory: true)
        try fileManager.createDirectory(at: workDir, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: workDir) }

        let copy = workDir.appendingPathComponent("chat.db")
        do {
            try fileManager.copyItem(at: databaseURL, to: copy)
        } catch {
            // 권한이 없으면 파일이 아예 안 보이기도 해서, 원본을 못 읽으면 모두 권한 문제로 본다.
            throw MessagesDatabaseError.accessDenied
        }
        for suffix in ["-wal", "-shm"] {
            let source = URL(fileURLWithPath: databaseURL.path + suffix)
            if fileManager.fileExists(atPath: source.path) {
                try? fileManager.copyItem(at: source, to: URL(fileURLWithPath: copy.path + suffix))
            }
        }
        return try query(copy, sender: sender)
    }

    private static func query(_ url: URL, sender: String) throws -> [RawMessage] {
        var db: OpaquePointer?
        guard sqlite3_open_v2(url.path, &db, SQLITE_OPEN_READWRITE, nil) == SQLITE_OK, let db else {
            let message = db.map { String(cString: sqlite3_errmsg($0)) } ?? "열 수 없음"
            sqlite3_close(db)
            throw MessagesDatabaseError.sqlite(message)
        }
        defer { sqlite3_close(db) }

        let sql = """
            SELECT m.ROWID, m.date, m.text, m.attributedBody
            FROM message m
            JOIN handle h ON m.handle_id = h.ROWID
            WHERE h.id = ?
            ORDER BY m.date ASC
            """
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else {
            throw MessagesDatabaseError.sqlite(String(cString: sqlite3_errmsg(db)))
        }
        defer { sqlite3_finalize(statement) }

        let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
        sqlite3_bind_text(statement, 1, sender, -1, transient)

        var messages: [RawMessage] = []
        while true {
            let step = sqlite3_step(statement)
            if step == SQLITE_DONE { break }
            guard step == SQLITE_ROW else {
                throw MessagesDatabaseError.sqlite(String(cString: sqlite3_errmsg(db)))
            }
            let text = sqlite3_column_text(statement, 2).map { String(cString: $0) }
            var body: Data?
            if let blob = sqlite3_column_blob(statement, 3) {
                body = Data(bytes: blob, count: Int(sqlite3_column_bytes(statement, 3)))
            }
            messages.append(RawMessage(
                rowID: sqlite3_column_int64(statement, 0),
                date: sqlite3_column_int64(statement, 1),
                text: text,
                attributedBody: body
            ))
        }
        return messages
    }
}
