// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "CardMan",
    platforms: [.macOS(.v14)],
    targets: [
        // 문자 해석, 메시지 DB 읽기, 집계, 저장. UI 없이 테스트할 수 있다.
        .target(name: "CardManCore"),
        // 메뉴바 + 상세 창 SwiftUI 앱
        .executableTarget(name: "CardMan", dependencies: ["CardManCore"]),
        .testTarget(name: "CardManCoreTests", dependencies: ["CardManCore"]),
    ]
)
