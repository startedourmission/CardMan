import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3
import pandas as pd
import re
from datetime import datetime
import os
from pathlib import Path
from config import load_config, save_config, load_manual_transactions, add_manual_transaction

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

class MessageAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("카드맨")

        # 윈도우 크기
        window_width = 900
        window_height = 700

        # 화면 중앙 계산
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2

        # 중앙에 윈도우 배치
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # 설정 로드
        self.config = load_config()

        # 데이터 저장용
        self.daily_df = None
        self.monthly_df = None
        self.quarterly_df = None
        self.yearly_df = None

        # 메인 프레임
        main_frame = ttk.Frame(root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)

        # 제목
        title = ttk.Label(main_frame, text="카드맨", font=('Arial', 18, 'bold'))
        title.grid(row=0, column=0, pady=10)

        # 통계 요약 프레임
        self.summary_frame = ttk.LabelFrame(main_frame, text="소비 통계", padding="10")
        self.summary_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=10, padx=10)

        # 원화 사용 금액
        self.krw_label = ttk.Label(
            self.summary_frame,
            text="원화 사용: -",
            font=('Arial', 14, 'bold')
        )
        self.krw_label.grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)

        # 달러 사용 금액
        self.usd_label = ttk.Label(
            self.summary_frame,
            text="달러 사용: -",
            font=('Arial', 14, 'bold')
        )
        self.usd_label.grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)

        # 총 소비 금액
        self.total_label = ttk.Label(
            self.summary_frame,
            text="총 소비 금액: -",
            font=('Arial', 14)
        )
        self.total_label.grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)

        # 월 평균 소비 금액
        self.avg_label = ttk.Label(
            self.summary_frame,
            text="월 평균 소비: -",
            font=('Arial', 14)
        )
        self.avg_label.grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)

        self.summary_frame.columnconfigure(0, weight=1)
        self.summary_frame.columnconfigure(1, weight=1)

        # 탭 생성
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=10)

        # 각 탭별 프레임 및 Treeview 생성
        self.transactions_tab = self.create_tab("거래내역")
        self.daily_tab = self.create_tab("일별")
        self.monthly_tab = self.create_tab("월별")
        self.quarterly_tab = self.create_tab("분기별")
        self.yearly_tab = self.create_tab("연도별")

        self.notebook.add(self.transactions_tab, text="거래 내역")
        self.notebook.add(self.daily_tab, text="일별 집계")
        self.notebook.add(self.monthly_tab, text="월별 집계")
        self.notebook.add(self.quarterly_tab, text="분기별 집계")
        self.notebook.add(self.yearly_tab, text="연도별 집계")

        # 하단 컨트롤 프레임
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=10, padx=10)

        # 연간 예산 입력
        ttk.Label(bottom_frame, text="연간 예산(원):").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.budget_entry = ttk.Entry(bottom_frame, width=15)
        self.budget_entry.insert(0, str(self.config['yearly_budget']))
        self.budget_entry.grid(row=0, column=1, sticky=tk.W, pady=5, padx=5)

        # 전화번호 입력
        ttk.Label(bottom_frame, text="전화번호:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.phone_entry = ttk.Entry(bottom_frame, width=20)
        self.phone_entry.insert(0, self.config['phone_number'])
        self.phone_entry.grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)

        # 분석 버튼
        self.analyze_btn = ttk.Button(bottom_frame, text="분석 시작", command=self.analyze_messages)
        self.analyze_btn.grid(row=0, column=2, rowspan=2, padx=5)

        # CSV 내보내기 버튼
        self.export_btn = ttk.Button(bottom_frame, text="CSV 내보내기", command=self.export_csv, state='disabled')
        self.export_btn.grid(row=0, column=3, rowspan=2, padx=5)

        # 수동 거래 추가 버튼
        self.manual_btn = ttk.Button(bottom_frame, text="거래 수동 추가", command=self.add_manual_transaction_dialog)
        self.manual_btn.grid(row=0, column=4, rowspan=2, padx=5)

        # 상태 표시
        self.status_label = ttk.Label(bottom_frame, text="연간 예산과 전화번호를 입력하고 '분석 시작'을 클릭하세요")
        self.status_label.grid(row=0, column=5, rowspan=2, sticky=tk.W, padx=10)

        # 앱 시작시 자동으로 분석 실행
        self.root.after(100, self.analyze_messages)

    def create_tab(self, period):
        """탭별 Treeview 생성"""
        frame = ttk.Frame(self.notebook)

        # Treeview와 스크롤바
        tree_scroll = ttk.Scrollbar(frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        tree = ttk.Treeview(frame, yscrollcommand=tree_scroll.set, height=20)
        tree.pack(fill=tk.BOTH, expand=True)

        tree_scroll.config(command=tree.yview)

        # 컬럼 설정
        if period == "거래내역":
            tree['columns'] = ('날짜', '금액', '가맹점')
            tree.heading('#0', text='번호')
            tree.column('#0', width=50)
            tree.heading('날짜', text='날짜')
            tree.column('날짜', width=150, anchor=tk.CENTER)
            tree.heading('금액', text='금액')
            tree.column('금액', width=120, anchor=tk.CENTER)
            tree.heading('가맹점', text='가맹점')
            tree.column('가맹점', width=250, anchor=tk.W)
        elif period == "일별":
            tree['columns'] = ('날짜', '금액', '건수', '누적금액')
        elif period == "월별":
            tree['columns'] = ('월', '금액', '건수', '누적금액')
        elif period == "분기별":
            tree['columns'] = ('분기', '금액', '건수', '누적금액')
        else:  # 연도별
            tree['columns'] = ('연도', '금액', '건수', '누적금액')

        if period != "거래내역":
            tree.heading('#0', text='번호')
            tree.column('#0', width=50)
            for col in tree['columns']:
                tree.heading(col, text=col)
                tree.column(col, width=150, anchor=tk.CENTER)

        # 프레임에 tree 저장
        frame.tree = tree
        return frame

    def update_treeview(self, tree, df):
        """Treeview 업데이트"""
        # 기존 데이터 삭제
        for item in tree.get_children():
            tree.delete(item)

        # 새 데이터 추가
        for idx, row in df.iterrows():
            values = [f"{row[col]:,}" if isinstance(row[col], (int, float)) else str(row[col])
                     for col in df.columns]
            tree.insert('', tk.END, text=str(idx+1), values=values)

    def log(self, message):
        """상태 메시지 업데이트"""
        self.status_label.config(text=message)
        self.root.update()

    def analyze_messages(self):
        phone_number = self.phone_entry.get()

        if not phone_number:
            messagebox.showerror("오류", "전화번호를 입력해주세요")
            return

        self.analyze_btn.config(state='disabled')

        try:
            self.log("메시지 데이터베이스 연결 중...")
            db_path = str(Path.home() / "Library" / "Messages" / "chat.db")
            conn = sqlite3.connect(db_path)

            self.log(f"전화번호 {phone_number}의 메시지 검색 중...")
            messages = pd.read_sql_query("""
                SELECT m.*
                FROM message m
                JOIN handle h ON m.handle_id = h.ROWID
                WHERE h.id = ?
                ORDER BY m.date ASC
            """, conn, params=[phone_number])

            self.log(f"총 {len(messages)}개 메시지 발견. 분석 중...")

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
                    # 가맹점명 추출 (취소 내역의 경우)
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

                    # 가맹점명 추출 (금액 다음 줄)
                    merchant_match = re.search(r'([\d,]+)원\n(.+?)\n', text)
                    merchant = merchant_match.group(2).strip() if merchant_match else ''

                    # 취소 여부 확인 (가맹점명이 "취소"로 끝나는 경우)
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

                # 해외 결제 금액 추출 (USD, EUR 등)
                foreign_match = re.search(r'([\d,]+\.?\d*)\((USD|EUR|JPY|CNY|GBP)\)', text)
                if foreign_match:
                    amount = float(foreign_match.group(1).replace(',', ''))
                    currency = foreign_match.group(2)

                    # 가맹점명 추출 (국가명 + 가맹점)
                    merchant_match = re.search(r'(미국|일본|중국|영국|프랑스|독일|캐나다|호주)\s+(.+?)\s+승인', text)
                    if merchant_match:
                        merchant = f"{merchant_match.group(1)} {merchant_match.group(2)}"
                    else:
                        merchant = ''

                    # 환율 적용 (대략적인 환율)
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

            # 수동 입력 거래 내역 로드 및 병합
            manual_transactions = load_manual_transactions()
            self.log(f"{len(manual_transactions)}개의 수동 입력 거래 발견")

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
                messagebox.showwarning("경고", "금액 정보가 포함된 메시지를 찾을 수 없습니다")
                self.log("금액 정보를 찾을 수 없습니다")
                return

            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')

            # 거래 내역용 DataFrame
            self.transactions_df = df[['date', 'amount', 'merchant']].copy()
            self.transactions_df.columns = ['날짜', '금액', '가맹점']
            self.transactions_df['날짜'] = self.transactions_df['날짜'].dt.strftime('%Y-%m-%d %H:%M')

            # 일별 집계
            self.daily_df = df.groupby(df['date'].dt.date).agg({
                'amount': ['sum', 'count']
            }).reset_index()
            self.daily_df.columns = ['날짜', '금액', '건수']
            self.daily_df['누적금액'] = self.daily_df['금액'].cumsum()

            # 월별 집계
            self.monthly_df = df.groupby(df['date'].dt.to_period('M')).agg({
                'amount': ['sum', 'count']
            }).reset_index()
            self.monthly_df.columns = ['월', '금액', '건수']
            self.monthly_df['누적금액'] = self.monthly_df['금액'].cumsum()

            # 분기별 집계
            self.quarterly_df = df.groupby(df['date'].dt.to_period('Q')).agg({
                'amount': ['sum', 'count']
            }).reset_index()
            self.quarterly_df.columns = ['분기', '금액', '건수']
            self.quarterly_df['누적금액'] = self.quarterly_df['금액'].cumsum()

            # 연도별 집계
            self.yearly_df = df.groupby(df['date'].dt.year).agg({
                'amount': ['sum', 'count']
            }).reset_index()
            self.yearly_df.columns = ['연도', '금액', '건수']
            self.yearly_df['누적금액'] = self.yearly_df['금액'].cumsum()

            # Treeview 업데이트
            self.log("결과를 표시하는 중...")
            self.update_treeview(self.transactions_tab.tree, self.transactions_df)
            self.update_treeview(self.daily_tab.tree, self.daily_df)
            self.update_treeview(self.monthly_tab.tree, self.monthly_df)
            self.update_treeview(self.quarterly_tab.tree, self.quarterly_df)
            self.update_treeview(self.yearly_tab.tree, self.yearly_df)

            # CSV 내보내기 버튼 활성화
            self.export_btn.config(state='normal')

            # 통계 요약 업데이트
            total_amount = df['amount'].sum()
            krw_amount = df[df['currency'] == 'KRW']['amount'].sum()
            usd_amount = df[df['currency'] == 'USD']['original_amount'].sum() if 'original_amount' in df.columns else 0
            months = len(self.monthly_df)
            avg_monthly = total_amount / months if months > 0 else 0

            # 연간 예산 및 진행률 계산
            try:
                yearly_budget = int(self.budget_entry.get())
                phone_number = self.phone_entry.get()

                # 설정 저장
                self.config['yearly_budget'] = yearly_budget
                self.config['phone_number'] = phone_number
                save_config(self.config)

                remaining = yearly_budget - total_amount
                percentage = (total_amount / yearly_budget) * 100
                budget_text = f"예산 사용: {percentage:.1f}% ({total_amount:,}원 / {yearly_budget:,}원)"
                remaining_text = f"잔여 예산: {remaining:,}원"
            except ValueError:
                budget_text = f"총 소비 금액: {total_amount:,}원"
                remaining_text = f"잔여 예산: 예산을 입력해주세요"

            self.krw_label.config(text=f"원화 사용: {krw_amount:,}원")
            self.usd_label.config(text=f"달러 사용: ${usd_amount:,.2f}")
            self.total_label.config(text=budget_text)
            self.avg_label.config(text=remaining_text)

            self.log(f"완료! 총 {len(data)}건의 거래 내역 분석 완료")

        except Exception as e:
            self.log(f"오류 발생: {str(e)}")
            messagebox.showerror("오류", f"오류가 발생했습니다:\n{str(e)}")

        finally:
            self.analyze_btn.config(state='normal')
            if 'conn' in locals():
                conn.close()

    def add_manual_transaction_dialog(self):
        """수동 거래 추가 다이얼로그"""
        dialog = tk.Toplevel(self.root)
        dialog.title("거래 수동 추가")
        dialog.geometry("400x250")

        # 중앙 배치
        dialog.transient(self.root)
        dialog.grab_set()

        # 입력 프레임
        input_frame = ttk.Frame(dialog, padding="20")
        input_frame.pack(fill=tk.BOTH, expand=True)

        # 날짜 입력
        ttk.Label(input_frame, text="날짜 (YYYY-MM-DD):").grid(row=0, column=0, sticky=tk.W, pady=5)
        date_entry = ttk.Entry(input_frame, width=20)
        date_entry.insert(0, datetime.now().strftime('%Y-%m-%d'))
        date_entry.grid(row=0, column=1, pady=5, padx=5)

        # 금액 입력
        ttk.Label(input_frame, text="금액 (원):").grid(row=1, column=0, sticky=tk.W, pady=5)
        amount_entry = ttk.Entry(input_frame, width=20)
        amount_entry.grid(row=1, column=1, pady=5, padx=5)

        # 가맹점 입력
        ttk.Label(input_frame, text="가맹점:").grid(row=2, column=0, sticky=tk.W, pady=5)
        merchant_entry = ttk.Entry(input_frame, width=20)
        merchant_entry.grid(row=2, column=1, pady=5, padx=5)

        # 통화 선택
        ttk.Label(input_frame, text="통화:").grid(row=3, column=0, sticky=tk.W, pady=5)
        currency_var = tk.StringVar(value='KRW')
        currency_combo = ttk.Combobox(input_frame, textvariable=currency_var, values=['KRW', 'USD', 'EUR', 'JPY'], width=17, state='readonly')
        currency_combo.grid(row=3, column=1, pady=5, padx=5)

        def save_transaction():
            try:
                date_str = date_entry.get()
                amount = int(amount_entry.get().replace(',', ''))
                merchant = merchant_entry.get()
                currency = currency_var.get()

                if not merchant:
                    messagebox.showerror("오류", "가맹점명을 입력해주세요")
                    return

                # 날짜 유효성 검사
                datetime.strptime(date_str, '%Y-%m-%d')

                # 거래 추가
                if add_manual_transaction(date_str, amount, merchant, currency):
                    messagebox.showinfo("완료", "거래가 추가되었습니다")
                    dialog.destroy()
                    # 자동으로 다시 분석
                    self.analyze_messages()
                else:
                    messagebox.showerror("오류", "거래 추가에 실패했습니다")

            except ValueError as e:
                messagebox.showerror("오류", f"입력값이 올바르지 않습니다:\n{str(e)}")

        # 버튼 프레임
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=10)

        ttk.Button(button_frame, text="추가", command=save_transaction).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="취소", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

    def export_csv(self):
        """CSV 파일 내보내기"""
        if self.daily_df is None:
            messagebox.showwarning("경고", "먼저 분석을 실행해주세요")
            return

        folder = filedialog.askdirectory(initialdir=str(Path.home() / "Desktop"))
        if not folder:
            return

        try:
            self.transactions_df.to_csv(os.path.join(folder, 'transactions.csv'), index=False, encoding='utf-8-sig')
            self.daily_df.to_csv(os.path.join(folder, 'daily.csv'), index=False, encoding='utf-8-sig')
            self.monthly_df.to_csv(os.path.join(folder, 'monthly.csv'), index=False, encoding='utf-8-sig')
            self.quarterly_df.to_csv(os.path.join(folder, 'quarterly.csv'), index=False, encoding='utf-8-sig')
            self.yearly_df.to_csv(os.path.join(folder, 'yearly.csv'), index=False, encoding='utf-8-sig')

            self.log(f"CSV 파일 저장 완료: {folder}")
            messagebox.showinfo("완료", f"CSV 파일이 저장되었습니다!\n위치: {folder}")
        except Exception as e:
            messagebox.showerror("오류", f"CSV 저장 중 오류 발생:\n{str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = MessageAnalyzerApp(root)
    root.mainloop()
