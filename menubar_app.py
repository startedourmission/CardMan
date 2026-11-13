import os
import rumps
import pandas as pd
import re
from datetime import datetime
from pathlib import Path
import subprocess
import sys
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSAttributedString,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSImage,
)
from rumps.rumps import NSApp as RumpsNSApp
from config import (
    load_config,
    load_manual_transactions,
    load_excluded_transaction_keys,
    is_messages_access_error,
    connect_messages_db,
    close_messages_db,
    open_full_disk_access_settings,
    prompt_full_disk_access,
    ensure_main_app_running,
    cardman_bundle_running,
)

def decode_message(row):
    msg_text = row['text']
    msg_attributed_body = row['attributedBody']

    if isinstance(msg_text, str) and msg_text:
        return msg_text

    body = ''
    if msg_attributed_body is None or (
        isinstance(msg_attributed_body, float) and pd.isna(msg_attributed_body)
    ):
        return ''

    try:
        msg_attributed_body = msg_attributed_body.decode('utf-8', errors='replace')
    except AttributeError:
        msg_attributed_body = str(msg_attributed_body)

    if "NSNumber" in msg_attributed_body:
        msg_attributed_body = msg_attributed_body.split("NSNumber")[0]
        if "NSString" in msg_attributed_body:
            msg_attributed_body = msg_attributed_body.split("NSString")[1]
            if "NSDictionary" in msg_attributed_body:
                msg_attributed_body = msg_attributed_body.split("NSDictionary")[0]
                body = msg_attributed_body[6:-12]
    return body if isinstance(body, str) else ''


def _handle_reopen(_self, _application, _flag):
    """응용프로그램의 CardMan을 다시 누르면 창을 앞으로 가져온다."""
    ensure_main_app_running()
    try:
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        pass
    return True


def _status_image(text):
    font = NSFont.menuBarFontOfSize_(14.0)
    attrs = {
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: NSColor.blackColor(),
    }
    rendered = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
    size = rendered.size()
    width = max(float(size.width) + 8.0, 22.0)
    height = 18.0
    image = NSImage.alloc().initWithSize_((width, height))
    image.lockFocus()
    rendered.drawAtPoint_((4.0, (height - float(size.height)) / 2.0))
    image.unlockFocus()
    image.setTemplate_(True)
    return image


def _apply_status_item(item, text):
    if item is None:
        return
    title = text or "카드맨"
    item.setVisible_(True)
    item.setLength_(-1)
    button = item.button()
    if button is None:
        item.setTitle_(title)
        return
    button.setHidden_(False)
    button.setAppearsDisabled_(False)
    button.setImage_(_status_image(title))
    button.setTitle_("")
    button.setToolTip_("카드맨")


def _patched_initialize_status_bar(self):
    _ORIGINAL_INITIALIZE_STATUS_BAR(self)
    title = self._app.get("_title") or self._app.get("_name") or "카드맨"
    _apply_status_item(getattr(self, "nsstatusitem", None), title)
    try:
        Path("/tmp/cardman-menubar.log").write_text(
            f"status item ready title={title!r}\n",
            encoding="utf-8",
        )
    except Exception:
        pass


def _patched_set_status_bar_title(self):
    title = self._app.get("_title") or self._app.get("_name") or "카드맨"
    _apply_status_item(getattr(self, "nsstatusitem", None), title)


_ORIGINAL_INITIALIZE_STATUS_BAR = RumpsNSApp.initializeStatusBar
RumpsNSApp.applicationShouldHandleReopen_hasVisibleWindows_ = _handle_reopen
RumpsNSApp.initializeStatusBar = _patched_initialize_status_bar
RumpsNSApp.setStatusBarTitle = _patched_set_status_bar_title


class CardManMenuBar(rumps.App):
    def __init__(self):
        super(CardManMenuBar, self).__init__("카드맨", title="카드맨", quit_button=None)

        # 설정 로드
        config = load_config()
        self.phone_number = config['phone_number']
        self.yearly_budget = config['yearly_budget']
        self.stats = None
        self._access_denied = False
        self._booted = False
        self.menu = [
            rumps.MenuItem("카드맨", callback=self.open_main_app),
            rumps.separator,
            rumps.MenuItem("통계 새로고침", callback=self.refresh_stats),
            rumps.MenuItem("접근 권한 설정", callback=self.open_permission_settings),
            rumps.separator,
            rumps.MenuItem("총 소비: 로딩중...", callback=self.dummy_callback),
            rumps.MenuItem("월 평균: 로딩중...", callback=self.dummy_callback),
            rumps.MenuItem("원화 사용: 로딩중...", callback=self.dummy_callback),
            rumps.MenuItem("달러 사용: 로딩중...", callback=self.dummy_callback),
            rumps.separator,
            rumps.MenuItem("최근 거래 내역", callback=self.dummy_callback),
            rumps.separator,
            rumps.MenuItem("종료", callback=rumps.quit_application)
        ]

    def _sync_status_item(self, text):
        """최신 macOS 메뉴바 버튼에 아이콘을 직접 그린다."""
        self._title = text
        nsapp = getattr(self, "_nsapp", None)
        item = getattr(nsapp, "nsstatusitem", None) if nsapp is not None else None
        _apply_status_item(item, text)

    def dummy_callback(self, _):
        """정보 표시용 메뉴 항목을 활성화된 것처럼 보이게 하는 더미 콜백"""
        pass

    def create_progress_bar(self, percentage):
        """프로그레스 바 생성"""
        bar_length = 10
        filled = int(bar_length * percentage / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        return f"{bar} {percentage:.0f}%"

    def update_title(self):
        """메뉴바 아이콘 업데이트"""
        if self.stats:
            yearly_spent = self.stats['total']
            percentage = (yearly_spent / self.yearly_budget) * 100

            # 예산 초과시 경고 표시
            if percentage > 100:
                text = f"⚠️ {percentage:.0f}%"
            else:
                text = f"₩ {percentage:.0f}%"
        else:
            text = "카드맨"
        self._sync_status_item(text)

    @rumps.timer(0.2)
    def _boot(self, timer):
        if self._booted:
            return
        self._booted = True
        try:
            timer.stop()
        except Exception:
            pass
        # 메뉴바 프로세스는 Dock에 안 띄운다. Dock 아이콘은 상세 창(app.py) 하나만.
        try:
            NSApplication.sharedApplication().setActivationPolicy_(
                NSApplicationActivationPolicyAccessory
            )
        except Exception:
            pass
        self._sync_status_item(self.title or "카드맨")
        ensure_main_app_running()
        self.refresh_stats(None)

    @rumps.clicked("카드맨")
    def open_main_app(self, _):
        """카드맨 Tkinter 앱 실행"""
        app_path = Path(__file__).parent / "app.py"
        try:
            subprocess.Popen([sys.executable, str(app_path)])
            print("카드맨 앱 실행")
        except Exception as e:
            print(f"앱 실행 실패: {str(e)}")

    def open_permission_settings(self, _):
        """전체 디스크 접근 권한 설정 화면 열기"""
        open_full_disk_access_settings()

    def analyze_messages(self):
        """메시지 분석 로직 (기존 app.py에서 가져옴)"""
        self._access_denied = False
        conn = None
        try:
            conn = connect_messages_db()

            messages = pd.read_sql_query("""
                SELECT m.ROWID AS message_id, m.*
                FROM message m
                JOIN handle h ON m.handle_id = h.ROWID
                WHERE h.id = ?
                ORDER BY m.date ASC
            """, conn, params=[self.phone_number])

            # 메시지 디코딩 및 금액 추출
            data = []
            for i in range(len(messages)):
                text = decode_message(messages.iloc[i])

                # iMessage date 변환
                timestamp = messages.iloc[i]['date'] / 1_000_000_000 + 978307200
                date = pd.Timestamp(datetime.fromtimestamp(timestamp))

                # 취소 내역 확인
                cancel_match = re.search(r'취소완료\s+\(-?([\d,]+)원\)', text)
                if cancel_match:
                    amount = -int(cancel_match.group(1).replace(',', ''))
                    merchant_match = re.search(r'\]\s+(.+?)\s+\d+월\d+일', text)
                    merchant = merchant_match.group(1).strip() if merchant_match else '[취소]'

                    data.append({
                        'date': date,
                        'amount': amount,
                        'currency': 'KRW',
                        'merchant': f"[취소] {merchant}",
                        'text': text,
                        'transaction_key': f"message:{messages.iloc[i]['message_id']}"
                    })
                    continue

                # 원화 금액 추출
                amount_match = re.search(r'([\d,]+)원', text)
                if amount_match:
                    amount = int(amount_match.group(1).replace(',', ''))

                    # 가맹점명 추출
                    merchant_match = re.search(r'([\d,]+)원\n(.+?)\n', text)
                    merchant = merchant_match.group(2).strip() if merchant_match else ''

                    # 취소 여부 확인
                    if merchant.endswith('취소'):
                        amount = -amount
                        merchant = f"[취소] {merchant[:-2].strip()}"

                    data.append({
                        'date': date,
                        'amount': amount,
                        'currency': 'KRW',
                        'merchant': merchant,
                        'text': text,
                        'transaction_key': f"message:{messages.iloc[i]['message_id']}"
                    })
                    continue

                # 해외 결제 금액 추출
                foreign_match = re.search(r'([\d,]+\.?\d*)\((KRW|USD|EUR|JPY|CNY|GBP)\)', text)
                if foreign_match:
                    amount = float(foreign_match.group(1).replace(',', ''))
                    currency = foreign_match.group(2)

                    # 가맹점명 추출
                    merchant_match = re.search(r'(미국|일본|중국|영국|프랑스|독일|캐나다|호주)\s+(.+?)\s+승인', text)
                    if merchant_match:
                        merchant = f"{merchant_match.group(1)} {merchant_match.group(2)}"
                    else:
                        merchant = ''

                    # 환율 적용
                    exchange_rates = {
                        'KRW': 1,
                        'USD': 1400,
                        'EUR': 1400,
                        'JPY': 9,
                        'CNY': 180,
                        'GBP': 1650
                    }
                    krw_amount = int(amount * exchange_rates.get(currency, 1))

                    data.append({
                        'date': date,
                        'amount': krw_amount,
                        'currency': currency,
                        'original_amount': amount,
                        'merchant': merchant,
                        'text': text,
                        'transaction_key': f"message:{messages.iloc[i]['message_id']}"
                    })

            close_messages_db(conn)
            conn = None

            # 수동 입력 거래 내역 로드 및 병합
            manual_transactions = load_manual_transactions()
            print(f"{len(manual_transactions)}개의 수동 입력 거래 발견")

            for manual in manual_transactions:
                data.append({
                    'date': pd.to_datetime(manual['date']),
                    'amount': manual['amount'],
                    'currency': manual.get('currency', 'KRW'),
                    'merchant': f"[수동] {manual['merchant']}",
                    'text': '',
                    'manual': True,
                    'transaction_key': f"manual:{manual['id']}"
                })

            if not data:
                return None

            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            excluded_keys = load_excluded_transaction_keys()
            df['budget_excluded'] = df['transaction_key'].isin(excluded_keys)
            budget_df = df[~df['budget_excluded']]

            # 올해 데이터만 필터링
            current_year = datetime.now().year
            df_this_year = budget_df[budget_df['date'].dt.year == current_year]

            # 통계 계산 (올해 데이터만)
            total_amount = df_this_year['amount'].sum()
            krw_amount = df_this_year[df_this_year['currency'] == 'KRW']['amount'].sum()
            usd_amount = df_this_year[df_this_year['currency'] == 'USD']['original_amount'].sum() if 'original_amount' in df_this_year.columns else 0

            # 이번 달 데이터 필터링
            current_month = datetime.now().month
            df_this_month = df_this_year[df_this_year['date'].dt.month == current_month]
            monthly_spent = df_this_month['amount'].sum()

            # 월별 집계 (올해 데이터만)
            monthly_df = df_this_year.groupby(df_this_year['date'].dt.to_period('M')).agg({
                'amount': ['sum', 'count']
            }).reset_index()
            months = len(monthly_df)
            avg_monthly = total_amount / months if months > 0 else 0

            # 최근 5개 거래
            recent_transactions = df.tail(5)[
                ['date', 'amount', 'merchant', 'budget_excluded']
            ].copy()
            recent_transactions['date'] = recent_transactions['date'].dt.strftime('%m/%d %H:%M')

            return {
                'total': total_amount,
                'krw': krw_amount,
                'usd': usd_amount,
                'avg_monthly': avg_monthly,
                'monthly_spent': monthly_spent,
                'recent': recent_transactions.to_dict('records')
            }

        except Exception as e:
            print(f"오류 발생: {str(e)}")
            if is_messages_access_error(e):
                self._access_denied = True
                prompt_full_disk_access()
            return None
        finally:
            if conn is not None:
                close_messages_db(conn)

    @rumps.clicked("통계 새로고침")
    def refresh_stats(self, _):
        """통계 새로고침"""
        print("통계 업데이트 중...")

        # 설정 다시 로드
        config = load_config()
        self.phone_number = config['phone_number']
        self.yearly_budget = config['yearly_budget']

        self.stats = self.analyze_messages()

        if self.stats:
            # 메뉴바 아이콘 업데이트
            self.update_title()

            # 연간 예산 진행률 계산
            yearly_spent = self.stats['total']
            remaining = self.yearly_budget - yearly_spent
            percentage = (yearly_spent / self.yearly_budget) * 100
            progress_bar = self.create_progress_bar(min(percentage, 100))

            # 메뉴 업데이트
            self.menu["총 소비: 로딩중..."].title = f"올해 총: {yearly_spent:,.0f}원 / {self.yearly_budget:,}원"
            self.menu["월 평균: 로딩중..."].title = f"한도: {progress_bar}"
            self.menu["원화 사용: 로딩중..."].title = f"잔여: {remaining:,.0f}원"
            self.menu["달러 사용: 로딩중..."].title = f"달러: ${self.stats['usd']:,.2f}"

            # 최근 거래 내역 업데이트
            # 기존 거래 내역 메뉴 아이템 제거
            menu_items = list(self.menu.keys())
            start_idx = menu_items.index("최근 거래 내역") + 1
            end_idx = menu_items.index("종료")

            for i in range(start_idx, end_idx):
                if menu_items[i] != "":
                    del self.menu[menu_items[i]]

            # 새로운 거래 내역 추가
            insert_idx = start_idx
            for transaction in self.stats['recent'][::-1]:  # 최신순
                marker = "⊘ " if transaction['budget_excluded'] else ""
                title = f"{marker}{transaction['date']} | {transaction['amount']:,}원 | {transaction['merchant'][:20]}"
                self.menu.insert_before("종료", rumps.MenuItem(title, callback=self.dummy_callback))

            print(f"업데이트 완료 - 총 소비: {self.stats['total']:,}원")
        elif self._access_denied:
            self._sync_status_item("⚠️")
            self.menu["총 소비: 로딩중..."].title = "메시지 접근 권한 필요"
            self.menu["월 평균: 로딩중..."].title = "설정에서 전체 디스크 접근을 허용하세요"
            self.menu["원화 사용: 로딩중..."].title = "권한 허용 후 새로고침"
            self.menu["달러 사용: 로딩중..."].title = "'접근 권한 설정' 메뉴를 확인하세요"
            print("오류: 메시지 데이터베이스에 접근할 수 없습니다")
        else:
            print("오류: 통계를 불러올 수 없습니다")


def _kill_other_menubars():
    me = str(os.getpid())
    script = str(Path(__file__).resolve())
    try:
        output = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True)
    except Exception:
        return
    for line in output.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        pid, cmd = parts
        if pid == me:
            continue
        if "python" in cmd and cmd.rstrip().endswith(script):
            try:
                os.kill(int(pid), 15)
            except OSError:
                pass


if __name__ == "__main__":
    if os.environ.get("CARDMAN_BUNDLED") != "1" and cardman_bundle_running():
        print("CardMan.app 메뉴바가 이미 실행 중입니다")
        sys.exit(0)
    if os.environ.get("CARDMAN_BUNDLED") == "1":
        ensure_main_app_running()
    _kill_other_menubars()
    CardManMenuBar().run()
