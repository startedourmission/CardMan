import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

CONFIG_FILE = Path.home() / ".cardman_config.json"
MANUAL_TRANSACTIONS_FILE = Path.home() / ".cardman_manual_transactions.json"
EXCLUDED_TRANSACTIONS_FILE = Path.home() / ".cardman_excluded_transactions.json"
PROJECT_ROOT = Path(__file__).resolve().parent


def _python_script_pid(script_name):
    script = str(PROJECT_ROOT / script_name)
    me = str(os.getpid())
    try:
        output = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True)
    except Exception:
        return None
    for line in output.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        pid, cmd = parts
        if pid == me:
            continue
        if "python" in cmd and cmd.rstrip().endswith(script):
            return pid
    return None


def _python_script_running(script_name):
    return _python_script_pid(script_name) is not None


def _activate_pid(pid):
    subprocess.run(
        [
            "osascript",
            "-e",
            f'tell application "System Events" to set frontmost of (first process whose unix id is {int(pid)}) to true',
        ],
        capture_output=True,
        check=False,
    )


def cardman_bundle_running():
    try:
        output = subprocess.check_output(["ps", "-ax", "-o", "command="], text=True)
    except Exception:
        return False
    return any(
        line.startswith(f"{bundle}/Contents/MacOS/CardMan")
        for line in output.splitlines()
        for bundle in ("/Applications/CardMan.app", str(PROJECT_ROOT / "CardMan.app"))
    )


def ensure_menubar_running():
    """상세 앱을 열 때 메뉴바가 없으면 같이 띄운다."""
    # CardMan.app은 자체 메뉴바 아이콘이 있어서 rumps 메뉴바를 또 띄우면 두 개가 된다.
    if os.environ.get("CARDMAN_BUNDLED") == "1" or cardman_bundle_running():
        return
    if _python_script_running("menubar_app.py"):
        return
    subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "menubar_app.py")],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def ensure_main_app_running():
    """카드맨.app을 누르면 상세 창을 앞으로 연다."""
    if Path(sys.argv[0]).name == "app.py":
        return
    pid = _python_script_pid("app.py")
    if pid:
        _activate_pid(pid)
        return
    subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "app.py")],
        start_new_session=True,
    )

def load_config():
    """설정 파일 로드"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass

    # 기본 설정
    return {
        'yearly_budget': 1800000,
        'phone_number': '+8215881688'
    }

def save_config(config):
    """설정 파일 저장"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"설정 저장 실패: {e}")
        return False

def load_manual_transactions():
    """수동 입력 거래 내역 로드"""
    if MANUAL_TRANSACTIONS_FILE.exists():
        try:
            with open(MANUAL_TRANSACTIONS_FILE, 'r', encoding='utf-8') as f:
                transactions = json.load(f)

            # 기존 수동 거래에도 영구 식별자를 부여해 예산 제외 상태가
            # 다른 거래를 삭제한 뒤에도 같은 거래에 유지되도록 한다.
            changed = False
            for transaction in transactions:
                if 'id' not in transaction:
                    transaction['id'] = uuid4().hex
                    changed = True

            if changed:
                save_manual_transactions(transactions)

            return transactions
        except Exception as e:
            print(f"수동 거래 내역 로드 실패: {e}")
    return []

def save_manual_transactions(transactions):
    """수동 입력 거래 내역 저장"""
    try:
        with open(MANUAL_TRANSACTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(transactions, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"수동 거래 내역 저장 실패: {e}")
        return False

def add_manual_transaction(date_str, amount, merchant, currency='KRW'):
    """수동 거래 추가"""
    transactions = load_manual_transactions()

    new_transaction = {
        'id': uuid4().hex,
        'date': date_str,
        'amount': amount,
        'merchant': merchant,
        'currency': currency,
        'manual': True
    }

    transactions.append(new_transaction)
    return save_manual_transactions(transactions)

def delete_manual_transaction(index):
    """수동 거래 삭제"""
    transactions = load_manual_transactions()
    if 0 <= index < len(transactions):
        transactions.pop(index)
        return save_manual_transactions(transactions)
    return False

def load_excluded_transaction_keys():
    """예산 합계에서 제외할 거래 식별자 로드"""
    if EXCLUDED_TRANSACTIONS_FILE.exists():
        try:
            with open(EXCLUDED_TRANSACTIONS_FILE, 'r', encoding='utf-8') as f:
                keys = json.load(f)
            if isinstance(keys, list):
                return set(str(key) for key in keys)
        except Exception as e:
            print(f"예산 제외 거래 로드 실패: {e}")
    return set()

def save_excluded_transaction_keys(keys):
    """예산 합계에서 제외할 거래 식별자 저장"""
    try:
        with open(EXCLUDED_TRANSACTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(sorted(set(keys)), f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"예산 제외 거래 저장 실패: {e}")
        return False


MESSAGES_DB_PATH = Path.home() / "Library" / "Messages" / "chat.db"
FULL_DISK_ACCESS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
)
MESSAGES_ACCESS_ALERT_TITLE = "메시지 접근 권한이 필요합니다"


def messages_python_path():
    """메시지 DB를 여는 실제 Python 실행 파일"""
    return Path(os.path.realpath(sys.executable))


def launching_app_name():
    """카드맨을 실행한 상위 앱 이름 (터미널/Grok 등)"""
    pid = os.getpid()
    for _ in range(12):
        try:
            comm = subprocess.check_output(
                ["ps", "-o", "comm=", "-p", str(pid)],
                text=True,
            ).strip()
        except Exception:
            break
        lower = comm.lower()
        if "grok" in lower:
            return "Grok"
        if comm in {"Terminal", "iTerm2", "iTerm", "Cursor", "Code", "Warp", "kitty"}:
            return comm
        try:
            ppid = subprocess.check_output(
                ["ps", "-o", "ppid=", "-p", str(pid)],
                text=True,
            ).strip()
        except Exception:
            break
        if not ppid or ppid in {"0", "1"} or ppid == str(pid):
            break
        pid = int(ppid)
    return None


def cardman_app_path():
    """설정 목록에 뜨는 카드맨.app 경로"""
    from macos_app import APPLICATIONS_BUNDLE, LOCAL_BUNDLE

    if APPLICATIONS_BUNDLE.exists():
        return APPLICATIONS_BUNDLE
    return LOCAL_BUNDLE


def messages_access_alert_text():
    app_path = cardman_app_path()
    return (
        "전체 디스크 접근 권한에 /Applications/CardMan.app 을 넣어야 합니다.\n"
        "터미널이나 Python을 허용해도 uv run에는 권한이 안 붙습니다.\n\n"
        f"{app_path}\n\n"
        "1. 목록에 있는 카드맨은 지우고, Finder의 CardMan을 다시 끌어다 놓기\n"
        "2. 켠 다음 다시 uv run menubar_app.py"
    )


def is_messages_access_error(exc):
    """메시지 DB를 열지 못한 권한/접근 오류인지 판별"""
    if isinstance(exc, PermissionError):
        return True
    message = str(exc).lower()
    return any(
        needle in message
        for needle in (
            "unable to open database file",
            "authorization denied",
            "operation not permitted",
            "permission denied",
        )
    )


_CONNECTION_OWNED_DIRS = {}
MESSAGES_DB_CACHE = Path.home() / "Library" / "Application Support" / "CardMan" / "messages"
MENUBAR_TITLE_FILE = Path.home() / "Library" / "Application Support" / "CardMan" / "menubar-title.txt"


def write_menubar_title(text):
    MENUBAR_TITLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    MENUBAR_TITLE_FILE.write_text(text, encoding="utf-8")


def _connect_copied_db(tmp_dir: Path, owned=False):
    dst = tmp_dir / "chat.db"
    if not dst.exists():
        raise PermissionError("unable to open database file")
    conn = sqlite3.connect(str(dst))
    if owned:
        _CONNECTION_OWNED_DIRS[id(conn)] = str(tmp_dir)
    return conn


def _copy_messages_files(src_dir: Path, dest_dir: Path) -> bool:
    dest_dir.mkdir(parents=True, exist_ok=True)
    # 이전 복사본의 WAL이 남아 있으면 새 chat.db와 섞여 깨질 수 있다.
    for name in ("chat.db-wal", "chat.db-shm"):
        (dest_dir / name).unlink(missing_ok=True)
    copied = False
    for name in ("chat.db", "chat.db-wal", "chat.db-shm"):
        src = src_dir / name
        try:
            if src.exists():
                shutil.copy2(src, dest_dir / name)
                copied = True
        except OSError:
            return False
    return copied and (dest_dir / "chat.db").exists()


def connect_messages_db():
    """Messages chat.db를 매번 새로 복사해서 연다.

    복사가 안 되면 예전 복사본으로 조용히 넘어가지 않고 권한 오류를 낸다.
    (예전 복사본을 쓰면 새로고침해도 숫자가 안 바뀐다.)
    """
    if _copy_messages_files(MESSAGES_DB_PATH.parent, MESSAGES_DB_CACHE):
        return _connect_copied_db(MESSAGES_DB_CACHE, owned=False)

    from macos_app import copy_messages_db_via_app

    copy_messages_db_via_app(MESSAGES_DB_CACHE)
    return _connect_copied_db(MESSAGES_DB_CACHE, owned=False)


def close_messages_db(conn):
    """메시지 DB 연결을 닫는다. 공유 복사본은 유지한다."""
    owned_dir = _CONNECTION_OWNED_DIRS.pop(id(conn), None)
    try:
        conn.close()
    finally:
        if owned_dir:
            shutil.rmtree(owned_dir, ignore_errors=True)


def open_full_disk_access_settings():
    """카드맨.app을 Finder에서 보여 주고 전체 디스크 접근 설정을 연다."""
    app_path = cardman_app_path()
    subprocess.run(["pbcopy"], input=str(app_path), text=True, check=False)
    if app_path.exists():
        subprocess.Popen(["open", "-R", str(app_path)])
    subprocess.Popen(["open", FULL_DISK_ACCESS_URL])


def prompt_full_disk_access():
    """권한 안내 팝업을 띄우고, 사용자가 동의하면 설정 화면을 연다"""
    script = """
on run argv
    set theText to item 1 of argv
    try
        set theResult to display dialog theText buttons {"나중에", "설정 열기"} default button "설정 열기" with title "메시지 접근 권한이 필요합니다" with icon caution
        return button returned of theResult
    on error
        return "나중에"
    end try
end run
"""
    result = subprocess.run(
        ["osascript", "-", messages_access_alert_text()],
        input=script,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and "설정 열기" in result.stdout:
        open_full_disk_access_settings()
        return True
    return False
