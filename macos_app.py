"""카드맨을 macOS 앱 번들로 만들어 전체 디스크 접근 권한 목록에 뜨게 한다."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
BUNDLE_NAME = "CardMan.app"
BUNDLE_ID = "com.startedourmission.cardman"
LOCAL_BUNDLE = PROJECT_ROOT / "CardMan.app"
APPLICATIONS_BUNDLE = Path("/Applications") / BUNDLE_NAME

LAUNCHER_SOURCE = r"""
#include <copyfile.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int copy_messages_db(const char *dest_dir) {
    const char *home = getenv("HOME");
    FILE *log = fopen("/tmp/cardman-copy.log", "w");
    if (!home || !dest_dir) {
        if (log) {
            fprintf(log, "missing home or dest\n");
            fclose(log);
        }
        return 1;
    }
    mkdir(dest_dir, 0700);
    const char *names[] = {"chat.db", "chat.db-wal", "chat.db-shm"};
    for (int i = 0; i < 3; i++) {
        char src[PATH_MAX];
        char dst[PATH_MAX];
        snprintf(src, sizeof(src), "%s/Library/Messages/%s", home, names[i]);
        snprintf(dst, sizeof(dst), "%s/%s", dest_dir, names[i]);
        if (copyfile(src, dst, NULL, COPYFILE_DATA) != 0) {
            if (log) {
                fprintf(log, "copyfile %s -> %s: %s\n", src, dst, strerror(errno));
            }
            if (i == 0) {
                if (log) fclose(log);
                return 1;
            }
        } else if (log) {
            fprintf(log, "copied %s\n", names[i]);
        }
    }
    if (log) {
        fprintf(log, "ok %s\n", dest_dir);
        fclose(log);
    }
    return 0;
}

int main(int argc, char **argv) {
    if (argc >= 3 && strcmp(argv[1], "--copy-db") == 0) {
        return copy_messages_db(argv[2]);
    }

    const char *python = "%PYTHON%";
    const char *script = "%SCRIPT%";
    char dest[PATH_MAX];
    snprintf(dest, sizeof(dest), "/tmp/cardman-messages-%d", getpid());
    if (copy_messages_db(dest) == 0) {
        setenv("CARDMAN_DB_COPY", dest, 1);
    }
    setenv("CARDMAN_BUNDLED", "1", 1);
    char *args[] = {(char *)python, (char *)script, NULL};
    execv(python, args);
    perror("카드맨 실행 실패");
    return 1;
}
"""

INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>ko</string>
    <key>CFBundleDisplayName</key>
    <string>카드맨</string>
    <key>CFBundleExecutable</key>
    <string>CardMan</string>
    <key>CFBundleIdentifier</key>
    <string>{bundle_id}</string>
    <key>CFBundleIconFile</key>
    <string>CardMan</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>카드맨</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>0.1.0</string>
    <key>CFBundleVersion</key>
    <string>0.1.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>LSUIElement</key>
    <false/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSAppleEventsUsageDescription</key>
    <string>카드맨이 권한 안내 창을 띄우기 위해 사용합니다.</string>
</dict>
</plist>
"""


def _c_string(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace('"', '\\"')


def _write_bundle(destination: Path) -> Path:
    python = PROJECT_ROOT / ".venv" / "bin" / "python3"
    app_script = PROJECT_ROOT / "app.py"
    menubar_script = PROJECT_ROOT / "menubar_app.py"
    if not python.exists():
        raise FileNotFoundError(f"venv python이 없습니다: {python}")

    macos_dir = destination / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir = destination / "Contents" / "Resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    icon = PROJECT_ROOT / "CardMan.icns"
    if icon.exists():
        shutil.copy2(icon, resources_dir / icon.name)
    (destination / "Contents" / "Info.plist").write_text(
        INFO_PLIST.format(bundle_id=BUNDLE_ID),
        encoding="utf-8",
    )
    (destination / "Contents" / "PkgInfo").write_text("APPL????", encoding="utf-8")

    source_template = (PROJECT_ROOT / "launcher.m").read_text(encoding="utf-8")
    source_path = macos_dir / "launcher.m"
    source_path.write_text(
        source_template.replace("%PYTHON%", _c_string(python))
        .replace("%APP_SCRIPT%", _c_string(app_script))
        .replace("%MENUBAR_SCRIPT%", _c_string(menubar_script)),
        encoding="utf-8",
    )
    binary = macos_dir / "CardMan"
    compile_result = subprocess.run(
        [
            "clang",
            "-fobjc-arc",
            "-finput-charset=UTF-8",
            "-Os",
            "-framework",
            "Cocoa",
            "-framework",
            "Foundation",
            "-o",
            str(binary),
            str(source_path),
        ],
        capture_output=True,
        text=True,
    )
    source_path.unlink(missing_ok=True)
    if compile_result.returncode != 0:
        raise RuntimeError(compile_result.stderr.strip() or "clang 컴파일 실패")
    os.chmod(binary, 0o755)

    _codesign(destination)
    subprocess.run(["xattr", "-cr", str(destination)], check=False)
    return destination


def _signing_identity() -> str | None:
    """고정 서명 인증서의 SHA-1. 없으면 None (ad-hoc 서명).

    ad-hoc 서명은 빌드할 때마다 바뀌어서 전체 디스크 접근 권한이 풀린다.
    인증서로 서명하면 다시 빌드해도 macOS가 같은 앱으로 본다.
    """
    override = os.environ.get("CARDMAN_SIGN_IDENTITY")
    if override:
        return override
    try:
        output = subprocess.check_output(
            ["security", "find-identity", "-v", "-p", "codesigning"],
            text=True,
        )
    except Exception:
        return None
    identities = []
    for line in output.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].endswith(")"):
            identities.append((parts[1], parts[2].strip('"')))
    for prefix in ("Developer ID Application:", "Apple Development:"):
        for sha1, name in identities:
            # 폐기된 인증서로 서명하면 macOS가 악성코드로 보고 실행을 막는다.
            if name.startswith(prefix) and not _certificate_revoked(sha1, name):
                return sha1
    return None


def _certificate_revoked(sha1: str, name: str) -> bool:
    """키체인 인증서가 OCSP 기준으로 폐기됐는지 확인한다. 확인 못 하면 폐기로 본다."""
    try:
        output = subprocess.check_output(
            ["security", "find-certificate", "-a", "-Z", "-p", "-c", name],
            text=True,
        )
    except Exception:
        return True
    pem_lines = []
    matched = False
    for line in output.splitlines():
        if line.startswith("SHA-1 hash:"):
            matched = line.split(":", 1)[1].strip() == sha1
            continue
        if matched:
            pem_lines.append(line)
            if line.startswith("-----END CERTIFICATE-----"):
                break
    if not pem_lines:
        return True
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".pem") as pem:
        pem.write("\n".join(pem_lines) + "\n")
        pem.flush()
        result = subprocess.run(
            ["security", "verify-cert", "-c", pem.name, "-p", "codeSign", "-R", "ocsp", "-L"],
            capture_output=True,
            text=True,
            check=False,
        )
    return result.returncode != 0


def _codesign(destination: Path) -> None:
    identity = _signing_identity()
    if identity:
        result = subprocess.run(
            [
                "codesign",
                "--force",
                "--sign",
                identity,
                "--timestamp=none",
                "--deep",
                str(destination),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return
        print(f"인증서 서명 실패, ad-hoc 서명으로 대신합니다: {result.stderr.strip()}")
    else:
        print("서명 인증서가 없어 ad-hoc 서명합니다. 다시 빌드하면 권한을 다시 줘야 합니다.")
    subprocess.run(
        ["codesign", "--force", "--sign", "-", "--deep", str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )


def _is_adhoc_signed(app: Path) -> bool:
    result = subprocess.run(
        ["codesign", "-dv", str(app)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode != 0 or "Signature=adhoc" in result.stderr


def _helper_supports_copy(app: Path) -> bool:
    binary = app / "Contents" / "MacOS" / "CardMan"
    if not binary.exists():
        return False
    result = subprocess.run(
        ["strings", str(binary)],
        capture_output=True,
        text=True,
        check=False,
    )
    return "cardman-launcher-v3" in (result.stdout or "")


def ensure_cardman_app(force: bool = False) -> Path:
    """카드맨.app을 만들고, 가능하면 /Applications에도 설치한다."""
    existing = APPLICATIONS_BUNDLE if APPLICATIONS_BUNDLE.exists() else LOCAL_BUNDLE
    # ad-hoc 서명된 옛 번들은 인증서가 생기면 한 번 다시 빌드해서 서명을 고정한다.
    needs_resign = _is_adhoc_signed(existing) and _signing_identity() is not None
    if not force and not needs_resign and _helper_supports_copy(existing):
        return existing

    if LOCAL_BUNDLE.exists():
        shutil.rmtree(LOCAL_BUNDLE)
    _write_bundle(LOCAL_BUNDLE)

    installed = LOCAL_BUNDLE
    try:
        if APPLICATIONS_BUNDLE.exists():
            shutil.rmtree(APPLICATIONS_BUNDLE)
        shutil.copytree(LOCAL_BUNDLE, APPLICATIONS_BUNDLE, copy_function=shutil.copy2)
        subprocess.run(["xattr", "-cr", str(APPLICATIONS_BUNDLE)], check=False)
        installed = APPLICATIONS_BUNDLE
    except OSError as e:
        print(f"/Applications 설치 실패, 프로젝트 앱을 사용합니다: {e}")

    unicode_legacy = Path("/Applications/카드맨.app")
    if unicode_legacy.exists() and unicode_legacy != APPLICATIONS_BUNDLE:
        shutil.rmtree(unicode_legacy, ignore_errors=True)

    lsregister = (
        Path("/System/Library/Frameworks/CoreServices.framework/Frameworks")
        / "LaunchServices.framework/Support/lsregister"
    )
    if lsregister.exists():
        subprocess.run(
            [str(lsregister), "-f", str(installed)],
            capture_output=True,
            text=True,
            check=False,
        )
    return installed


def copy_messages_db_via_app(dest_dir: Path) -> None:
    """LaunchServices로 카드맨.app을 띄워 Messages DB를 dest_dir로 복사한다."""
    app = ensure_cardman_app()
    dest_dir.mkdir(parents=True, exist_ok=True)
    # 예전 복사본이 남아 있으면 복사가 실패해도 성공한 것처럼 보인다.
    for name in ("chat.db", "chat.db-wal", "chat.db-shm"):
        (dest_dir / name).unlink(missing_ok=True)
    result = subprocess.run(
        [
            "open",
            "-n",
            "-W",
            str(app),
            "--args",
            "--copy-db",
            str(dest_dir),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if not (dest_dir / "chat.db").exists():
        detail = ""
        log = Path("/tmp/cardman-copy.log")
        if log.exists():
            detail = log.read_text(encoding="utf-8", errors="replace").strip()
        stderr = (result.stderr or "").strip()
        raise PermissionError(
            detail or stderr or "unable to open database file"
        )
