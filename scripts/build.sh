#!/bin/bash
# 카드맨을 빌드하고 Developer ID로 서명한다.
#
#   scripts/build.sh            build/CardMan.app 만들기
#   scripts/build.sh install    + /Applications 에 설치하고 실행
#   scripts/build.sh dmg        + build/CardMan-<버전>.dmg 만들고 공증
#
# 서명 인증서는 키체인의 "Developer ID Application" 을 자동으로 고른다. 바꾸려면 SIGN_IDENTITY.
# 공증은 notarytool 키체인 프로필(기본 이름 cardman)을 쓴다. 처음 한 번 등록:
#   xcrun notarytool store-credentials cardman --apple-id <애플 ID> --team-id <팀 ID>
set -euo pipefail

cd "$(dirname "$0")/.."

VERSION="${VERSION:-$(cat VERSION)}"
BUILD_NUMBER="${BUILD_NUMBER:-$(git rev-list --count HEAD 2>/dev/null || echo 1)}"
NOTARY_PROFILE="${NOTARY_PROFILE:-cardman}"
ACTION="${1:-app}"

BUILD_DIR="build"
APP="$BUILD_DIR/CardMan.app"

if [[ -z "${SIGN_IDENTITY:-}" ]]; then
    SIGN_IDENTITY="$(security find-identity -v -p codesigning \
        | sed -n 's/.*"\(Developer ID Application: .*\)"/\1/p' | head -1)"
fi
if [[ -z "$SIGN_IDENTITY" ]]; then
    echo "Developer ID Application 인증서가 키체인에 없습니다." >&2
    exit 1
fi

echo "▸ 빌드 (arm64 + x86_64) $VERSION ($BUILD_NUMBER)"
swift build -c release --arch arm64 --arch x86_64
BINARY="$(swift build -c release --arch arm64 --arch x86_64 --show-bin-path)/CardMan"

echo "▸ 앱 번들"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BINARY" "$APP/Contents/MacOS/CardMan"
cp Resources/CardMan.icns "$APP/Contents/Resources/CardMan.icns"
sed -e "s/__VERSION__/$VERSION/" -e "s/__BUILD__/$BUILD_NUMBER/" Resources/Info.plist > "$APP/Contents/Info.plist"

echo "▸ 서명: $SIGN_IDENTITY"
# 공증을 받으려면 hardened runtime(--options runtime)과 보안 타임스탬프가 필요하다.
codesign --force --options runtime --timestamp --sign "$SIGN_IDENTITY" "$APP"
codesign --verify --strict --verbose=2 "$APP"

notarize() {
    echo "▸ 공증: $1"
    xcrun notarytool submit "$1" --keychain-profile "$NOTARY_PROFILE" --wait
}

case "$ACTION" in
    app)
        ;;
    install)
        echo "▸ /Applications 에 설치"
        osascript -e 'tell application id "com.startedourmission.cardman" to quit' >/dev/null 2>&1 || true
        pkill -x CardMan >/dev/null 2>&1 || true
        rm -rf /Applications/CardMan.app
        ditto "$APP" /Applications/CardMan.app
        open /Applications/CardMan.app
        ;;
    dmg)
        # 1) 앱을 공증하고 티켓을 붙인다. 인터넷이 없어도 Gatekeeper가 바로 확인할 수 있다.
        ZIP="$BUILD_DIR/CardMan.zip"
        ditto -c -k --keepParent "$APP" "$ZIP"
        notarize "$ZIP"
        xcrun stapler staple "$APP"
        rm -f "$ZIP"

        # 2) 앱과 응용 프로그램 폴더 바로가기를 담은 DMG를 만들고 서명·공증한다.
        DMG="$BUILD_DIR/CardMan-$VERSION.dmg"
        STAGING="$BUILD_DIR/dmg"
        rm -rf "$STAGING" "$DMG"
        mkdir -p "$STAGING"
        ditto "$APP" "$STAGING/CardMan.app"
        ln -s /Applications "$STAGING/Applications"
        hdiutil create -volname "카드맨" -srcfolder "$STAGING" -fs HFS+ -format UDZO -ov "$DMG" >/dev/null
        rm -rf "$STAGING"
        codesign --force --timestamp --sign "$SIGN_IDENTITY" "$DMG"
        notarize "$DMG"
        xcrun stapler staple "$DMG"
        spctl --assess --type open --context context:primary-signature --verbose=2 "$DMG"
        echo "▸ 완료: $DMG"
        ;;
    *)
        echo "알 수 없는 동작: $ACTION (app | install | dmg)" >&2
        exit 1
        ;;
esac
