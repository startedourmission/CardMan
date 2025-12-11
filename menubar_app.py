import rumps
import sqlite3
import pandas as pd
import re
from datetime import datetime
from pathlib import Path
import subprocess
import sys
from config import load_config, load_manual_transactions

def decode_message(row):
    msg_text = row['text']
    msg_attributed_body = row['attributedBody']

    body=''
    if msg_text:
        body = msg_text
    elif msg_attributed_body is None:
        body = ''
    else:
        try:
            msg_attributed_body = msg_attributed_body.decode('utf-8', errors='replace')
        except AttributeError as err:
            pass

        if "NSNumber" in str(msg_attributed_body):
            msg_attributed_body = str(msg_attributed_body).split("NSNumber")[0]
            if "NSString" in msg_attributed_body:
                msg_attributed_body = str(msg_attributed_body).split("NSString")[1]
                if "NSDictionary" in msg_attributed_body:
                    msg_attributed_body = str(msg_attributed_body).split("NSDictionary")[0]
                    msg_attributed_body = msg_attributed_body[6:-12]
                    body = msg_attributed_body
    return body


class CardManMenuBar(rumps.App):
    def __init__(self):
        super(CardManMenuBar, self).__init__("₩", template=True, quit_button=None)

        # 설정 로드
        config = load_config()
        self.phone_number = config['phone_number']
        self.yearly_budget = config['yearly_budget']
        self.stats = None
        self.menu = [
            rumps.MenuItem("카드맨", callback=self.open_main_app),
            rumps.separator,
            rumps.MenuItem("통계 새로고침", callback=self.refresh_stats),
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

        # 앱 시작시 자동으로 통계 로드
        self.refresh_stats(None)

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
                self.title = f"⚠️ {percentage:.0f}%"
            else:
                self.title = f"₩ {percentage:.0f}%"
        else:
            self.title = "₩"

    @rumps.clicked("카드맨")
    def open_main_app(self, _):
        """카드맨 Tkinter 앱 실행"""
        app_path = Path(__file__).parent / "app.py"
        try:
            # uv run으로 실행
            subprocess.Popen(["uv", "run", str(app_path)])
            print("카드맨 앱 실행")
        except Exception as e:
            print(f"앱 실행 실패: {str(e)}")

    def analyze_messages(self):
        """메시지 분석 로직 (기존 app.py에서 가져옴)"""
        try:
            db_path = str(Path.home() / "Library" / "Messages" / "chat.db")
            conn = sqlite3.connect(db_path)

            messages = pd.read_sql_query("""
                SELECT m.*
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
                date = pd.to_datetime(timestamp, unit='s')

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
                        'text': text
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
                        'text': text
                    })
                    continue

                # 해외 결제 금액 추출
                foreign_match = re.search(r'([\d,]+\.?\d*)\((USD|EUR|JPY|CNY|GBP)\)', text)
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
                        'text': text
                    })

            conn.close()

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
                    'manual': True
                })

            if not data:
                return None

            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')

            # 올해 데이터만 필터링
            current_year = datetime.now().year
            df_this_year = df[df['date'].dt.year == current_year]

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
            recent_transactions = df.tail(5)[['date', 'amount', 'merchant']].copy()
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
            return None

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
                title = f"{transaction['date']} | {transaction['amount']:,}원 | {transaction['merchant'][:20]}"
                self.menu.insert_before("종료", rumps.MenuItem(title, callback=self.dummy_callback))

            print(f"업데이트 완료 - 총 소비: {self.stats['total']:,}원")
        else:
            print("오류: 통계를 불러올 수 없습니다")


if __name__ == "__main__":
    CardManMenuBar().run()
