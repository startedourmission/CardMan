import numbers
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox
import sqlite3
import pandas as pd
import re
from datetime import datetime
import os
from pathlib import Path
from config import (
    load_config,
    save_config,
    load_manual_transactions,
    add_manual_transaction,
    delete_manual_transaction,
    load_excluded_transaction_keys,
    save_excluded_transaction_keys,
    is_messages_access_error,
    connect_messages_db,
    close_messages_db,
    prompt_full_disk_access,
    ensure_menubar_running,
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


# 무채색 + 강조색(파랑) 하나. accent_* 는 같은 색의 농도만 다르다.
COLORS = {
    'bg': '#FFFFFF',
    'text': '#191F28',
    'muted': '#8B95A1',
    'faint': '#B0B8C1',
    'line': '#E5E8EB',
    'subtle': '#F2F4F6',
    'accent': '#3182F6',
    'accent_hover': '#1B64DA',
    'accent_disabled': '#A9C9FA',
    'accent_soft': '#E8F3FF',
}

AMOUNT_COLUMNS = ('금액', '누적금액')
NUMBER_COLUMNS = AMOUNT_COLUMNS + ('건수',)


class MessageAnalyzerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("카드맨")
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(400, lambda: self.root.attributes("-topmost", False))

        # 윈도우 크기
        window_width = 960
        window_height = 780

        # 화면 중앙 계산
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2

        # 중앙에 윈도우 배치
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.minsize(820, 640)
        self.root.configure(bg=COLORS['bg'])
        self.setup_style()

        # 설정 로드
        self.config = load_config()

        # 데이터 저장용
        self.daily_df = None
        self.monthly_df = None
        self.quarterly_df = None
        self.yearly_df = None
        self.transactions_df = None
        self.all_transactions_df = None
        self.excluded_transaction_keys = load_excluded_transaction_keys()
        self.transaction_item_keys = {}
        self.budget_ratio = 0.0

        # 메인 프레임
        main_frame = ttk.Frame(root, padding=(28, 22, 28, 16))
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(4, weight=1)

        # 헤더: 제목 + 새로고침
        header = ttk.Frame(main_frame)
        header.grid(row=0, column=0, sticky=(tk.W, tk.E))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="카드맨", style='Title.TLabel').grid(row=0, column=0, sticky=tk.W)
        self.analyze_btn = ttk.Button(
            header, text="새로고침", style='Accent.TButton', command=self.analyze_messages
        )
        self.analyze_btn.grid(row=0, column=1, sticky=tk.E)

        # 예산: 큰 숫자는 사용률 하나만
        budget = ttk.Frame(main_frame)
        budget.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(22, 0))
        budget.columnconfigure(0, weight=1)

        ttk.Label(budget, text=f"{datetime.now().year}년 예산 사용", style='Muted.TLabel').grid(
            row=0, column=0, sticky=tk.W
        )
        self.percent_label = ttk.Label(budget, text="-", style='Hero.TLabel')
        self.percent_label.grid(row=1, column=0, sticky=tk.W)
        self.remaining_label = ttk.Label(budget, text="")
        self.remaining_label.grid(row=1, column=1, sticky=(tk.E, tk.S), pady=(0, 10))

        self.progress = tk.Canvas(budget, height=6, bg=COLORS['bg'], highlightthickness=0)
        self.progress.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(4, 8))
        self.progress.bind('<Configure>', self.draw_progress)

        self.total_label = ttk.Label(budget, text="", style='Muted.TLabel')
        self.total_label.grid(row=3, column=0, columnspan=2, sticky=tk.W)

        # 보조 수치: 박스 없이 한 줄
        stats = ttk.Frame(main_frame)
        stats.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(24, 0))
        self.month_label = self.create_stat(stats, 0, "이번 달")
        self.avg_label = self.create_stat(stats, 1, "월평균")
        self.krw_label = self.create_stat(stats, 2, "원화 결제")
        self.usd_label = self.create_stat(stats, 3, "달러 결제")

        self.create_rule(main_frame).grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(24, 8))

        # 탭 생성
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

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

        # 하단: 설정 입력 + 보조 버튼
        self.create_rule(main_frame).grid(row=5, column=0, sticky=(tk.W, tk.E))
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=6, column=0, sticky=(tk.W, tk.E), pady=(14, 0))
        bottom_frame.columnconfigure(4, weight=1)

        # 연간 예산 입력 (엔터로 바로 다시 계산)
        ttk.Label(bottom_frame, text="연간 예산", style='Field.TLabel').grid(row=0, column=0, sticky=tk.W)
        self.budget_entry = ttk.Entry(bottom_frame, width=12)
        self.budget_entry.insert(0, str(self.config['yearly_budget']))
        self.budget_entry.grid(row=0, column=1, sticky=tk.W, padx=(8, 18))
        self.budget_entry.bind('<Return>', lambda _event: self.analyze_messages())

        # 전화번호 입력
        ttk.Label(bottom_frame, text="전화번호", style='Field.TLabel').grid(row=0, column=2, sticky=tk.W)
        self.phone_entry = ttk.Entry(bottom_frame, width=16)
        self.phone_entry.insert(0, self.config['phone_number'])
        self.phone_entry.grid(row=0, column=3, sticky=tk.W, padx=(8, 0))
        self.phone_entry.bind('<Return>', lambda _event: self.analyze_messages())

        # 보조 버튼
        self.manual_btn = ttk.Button(
            bottom_frame, text="수동 추가", style='Secondary.TButton',
            command=self.add_manual_transaction_dialog,
        )
        self.manual_btn.grid(row=0, column=5, padx=(0, 6))
        self.manage_manual_btn = ttk.Button(
            bottom_frame, text="수동 거래 관리", style='Secondary.TButton',
            command=self.manage_manual_transactions_dialog,
        )
        self.manage_manual_btn.grid(row=0, column=6, padx=(0, 6))
        self.export_btn = ttk.Button(
            bottom_frame, text="CSV 내보내기", style='Secondary.TButton',
            command=self.export_csv, state='disabled',
        )
        self.export_btn.grid(row=0, column=7)

        # 상태 표시
        self.status_label = ttk.Label(
            main_frame, text="메시지를 불러오는 중...", style='Status.TLabel'
        )
        self.status_label.grid(row=7, column=0, sticky=tk.W, pady=(10, 0))

        # 앱 시작시 자동으로 분석 실행
        self.root.after(100, self.analyze_messages)

    def setup_style(self):
        """색을 직접 지정할 수 있는 clam 테마를 무채색 + 강조색 하나로 맞춘다."""
        families = set(tkfont.families(self.root))
        self.font_family = next(
            (name for name in ('Pretendard', 'Apple SD Gothic Neo') if name in families),
            'TkDefaultFont',
        )
        C = COLORS
        style = ttk.Style(self.root)
        style.theme_use('clam')

        style.configure('.', font=self.font(13), background=C['bg'], foreground=C['text'])

        style.configure('Title.TLabel', font=self.font(17, 'bold'))
        style.configure('Hero.TLabel', font=self.font(34, 'bold'))
        style.configure('Muted.TLabel', foreground=C['muted'], font=self.font(12))
        style.configure('Field.TLabel', foreground=C['muted'], font=self.font(12))
        style.configure('Status.TLabel', foreground=C['muted'], font=self.font(11))
        style.configure('StatValue.TLabel', font=self.font(15))

        style.configure(
            'Accent.TButton', background=C['accent'], foreground='white',
            lightcolor=C['accent'], darkcolor=C['accent'], bordercolor=C['accent'],
            borderwidth=0, focusthickness=0, relief='flat',
            padding=(14, 6), font=self.font(13, 'bold'), width=0,
        )
        style.map(
            'Accent.TButton',
            background=[('disabled', C['accent_disabled']), ('active', C['accent_hover'])],
            lightcolor=[('disabled', C['accent_disabled']), ('active', C['accent_hover'])],
            darkcolor=[('disabled', C['accent_disabled']), ('active', C['accent_hover'])],
            bordercolor=[('disabled', C['accent_disabled']), ('active', C['accent_hover'])],
            foreground=[('disabled', 'white')],
        )
        style.configure(
            'Secondary.TButton', background=C['bg'], foreground=C['text'],
            lightcolor=C['bg'], darkcolor=C['bg'], bordercolor=C['line'],
            borderwidth=1, focusthickness=0, relief='solid', padding=(12, 5), width=0,
        )
        style.map(
            'Secondary.TButton',
            background=[('active', C['subtle'])],
            lightcolor=[('active', C['subtle'])],
            darkcolor=[('active', C['subtle'])],
            foreground=[('disabled', C['faint'])],
        )

        style.configure(
            'TEntry', fieldbackground=C['bg'], bordercolor=C['line'],
            lightcolor=C['bg'], darkcolor=C['bg'], padding=(8, 4),
        )
        style.map('TEntry', bordercolor=[('focus', C['accent'])], lightcolor=[('focus', C['accent'])])
        style.configure(
            'TCombobox', fieldbackground=C['bg'], background=C['bg'],
            bordercolor=C['line'], lightcolor=C['bg'], darkcolor=C['bg'], padding=(8, 4),
        )

        # 탭은 글자만: 선택된 탭은 진하게, 나머지는 흐리게
        style.configure(
            'TNotebook', borderwidth=0, tabmargins=(0, 0, 0, 0),
            bordercolor=C['bg'], lightcolor=C['bg'], darkcolor=C['bg'],
        )
        style.configure(
            'TNotebook.Tab', foreground=C['muted'], borderwidth=0,
            bordercolor=C['bg'], lightcolor=C['bg'], darkcolor=C['bg'],
            padding=(0, 6, 22, 6), font=self.font(13),
        )
        # clam은 선택 안 된 탭에 회색 배경/테두리를 따로 매핑해 두므로 둘 다 덮어쓴다
        style.map(
            'TNotebook.Tab',
            background=[('selected', C['bg']), ('!selected', C['bg'])],
            lightcolor=[('selected', C['bg']), ('!selected', C['bg'])],
            bordercolor=[('selected', C['bg']), ('!selected', C['bg'])],
            foreground=[('selected', C['text'])],
            font=[('selected', self.font(13, 'bold'))],
            expand=[('selected', (0, 0, 0, 0))],
            padding=[('selected', (0, 6, 22, 6))],
        )

        style.configure(
            'Treeview', fieldbackground=C['bg'], rowheight=30, borderwidth=0, font=self.font(13),
        )
        style.map('Treeview', background=[('selected', C['accent_soft'])], foreground=[('selected', C['text'])])
        style.layout('Treeview', [('Treeview.treearea', {'sticky': 'nswe'})])
        style.configure(
            'Treeview.Heading', foreground=C['muted'],
            bordercolor=C['line'], lightcolor=C['bg'], darkcolor=C['line'],
            relief='flat', padding=(6, 6), font=self.font(12),
        )
        style.map('Treeview.Heading', background=[('active', C['bg'])])

    def font(self, size, weight='normal'):
        return (self.font_family, size, weight)

    def create_rule(self, parent):
        """1px 가로 구분선"""
        return tk.Frame(parent, height=1, bg=COLORS['line'])

    def create_stat(self, parent, column, caption):
        """라벨 + 값 한 쌍을 만들고 값 라벨을 돌려준다."""
        parent.columnconfigure(column, weight=1, uniform='stat')
        cell = ttk.Frame(parent)
        cell.grid(row=0, column=column, sticky=tk.W)
        ttk.Label(cell, text=caption, style='Muted.TLabel').pack(anchor=tk.W)
        value = ttk.Label(cell, text="-", style='StatValue.TLabel')
        value.pack(anchor=tk.W, pady=(2, 0))
        return value

    def draw_progress(self, _event=None):
        """예산 진행바 (강조색 한 가지)"""
        canvas = self.progress
        canvas.delete('all')
        width = canvas.winfo_width()
        height = int(canvas['height'])
        if width <= height:
            return
        radius = height / 2
        canvas.create_line(
            radius, radius, width - radius, radius,
            width=height, capstyle=tk.ROUND, fill=COLORS['subtle'],
        )
        ratio = min(max(self.budget_ratio, 0.0), 1.0)
        if ratio <= 0:
            return
        end = radius + (width - height) * ratio
        canvas.create_line(
            radius, radius, max(end, radius + 0.5), radius,
            width=height, capstyle=tk.ROUND, fill=COLORS['accent'],
        )

    def create_tab(self, period):
        """탭별 Treeview 생성"""
        frame = ttk.Frame(self.notebook)

        # Treeview와 스크롤바 (스크롤바는 macOS 기본 모양)
        tree_scroll = tk.Scrollbar(frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        tree = ttk.Treeview(frame, yscrollcommand=tree_scroll.set, height=20)
        tree.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

        tree_scroll.config(command=tree.yview)

        # 컬럼 설정
        if period == "거래내역":
            tree['columns'] = ('날짜', '금액', '가맹점', '예산 제외')
            tree.heading('#0', text='번호')
            tree.column('#0', width=56, anchor=tk.CENTER, stretch=False)
            tree.heading('날짜', text='날짜', anchor=tk.W)
            tree.column('날짜', width=170, anchor=tk.W, stretch=False)
            tree.heading('금액', text='금액', anchor=tk.E)
            tree.column('금액', width=120, anchor=tk.E, stretch=False)
            tree.heading('가맹점', text='가맹점', anchor=tk.W)
            tree.column('가맹점', width=300, anchor=tk.W)
            tree.heading('예산 제외', text='예산 제외')
            tree.column('예산 제외', width=90, anchor=tk.CENTER, stretch=False)
            tree.tag_configure('excluded', foreground=COLORS['faint'])
            tree.bind('<ButtonRelease-1>', self.on_transaction_tree_click)
            tree.bind('<space>', self.on_transaction_tree_space)
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
            tree.column('#0', width=56, anchor=tk.CENTER, stretch=False)
            for col in tree['columns']:
                anchor = tk.E if col in NUMBER_COLUMNS else tk.W
                tree.heading(col, text=col, anchor=anchor)
                tree.column(col, width=150, anchor=anchor)

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
            values = []
            for col in df.columns:
                value = row[col]
                # 연도(2026)에는 쉼표를 찍지 않도록 금액/건수 컬럼만 숫자 서식을 쓴다
                if col in NUMBER_COLUMNS and isinstance(value, numbers.Number):
                    text = f"{value:,.0f}"
                    values.append(f"{text}원" if col in AMOUNT_COLUMNS else text)
                else:
                    values.append(str(value))
            tree.insert('', tk.END, text=str(idx+1), values=values)

    def update_transactions_treeview(self):
        """체크 가능한 거래 내역 Treeview 업데이트"""
        tree = self.transactions_tab.tree
        for item in tree.get_children():
            tree.delete(item)

        self.transaction_item_keys = {}
        for number, (_, row) in enumerate(self.all_transactions_df.iterrows(), start=1):
            item_id = f"transaction-{number}"
            excluded = bool(row['budget_excluded'])
            values = (
                row['date'].strftime('%Y-%m-%d %H:%M'),
                f"{row['amount']:,}원",
                row['merchant'],
                '☑' if excluded else '☐',
            )
            tags = ('excluded',) if excluded else ()
            tree.insert('', tk.END, iid=item_id, text=str(number), values=values, tags=tags)
            self.transaction_item_keys[item_id] = row['transaction_key']

        # 최신 거래가 바로 보이도록 맨 아래로 스크롤
        tree.yview_moveto(1.0)

    def on_transaction_tree_click(self, event):
        """예산 제외 셀 클릭 처리"""
        tree = self.transactions_tab.tree
        if tree.identify_region(event.x, event.y) != 'cell':
            return

        checkbox_column = f"#{list(tree['columns']).index('예산 제외') + 1}"
        if tree.identify_column(event.x) != checkbox_column:
            return

        item_id = tree.identify_row(event.y)
        if item_id:
            self.toggle_transaction_exclusion(item_id)
            return 'break'

    def on_transaction_tree_space(self, _event):
        """선택한 거래의 예산 제외 상태를 스페이스바로 전환"""
        selection = self.transactions_tab.tree.selection()
        if selection:
            self.toggle_transaction_exclusion(selection[0])
            return 'break'

    def toggle_transaction_exclusion(self, item_id):
        """거래 한 건의 예산 제외 상태 저장 및 통계 재계산"""
        transaction_key = self.transaction_item_keys.get(item_id)
        if not transaction_key:
            return

        updated_keys = set(self.excluded_transaction_keys)
        if transaction_key in updated_keys:
            updated_keys.remove(transaction_key)
            excluded = False
        else:
            updated_keys.add(transaction_key)
            excluded = True

        if not save_excluded_transaction_keys(updated_keys):
            messagebox.showerror("오류", "예산 제외 설정을 저장하지 못했습니다")
            return

        self.excluded_transaction_keys = updated_keys
        self.all_transactions_df['budget_excluded'] = (
            self.all_transactions_df['transaction_key'].isin(updated_keys)
        )
        self.refresh_analysis_views(update_transactions=False)

        tree = self.transactions_tab.tree
        tree.set(item_id, '예산 제외', '☑' if excluded else '☐')
        tags = [tag for tag in tree.item(item_id, 'tags') if tag != 'excluded']
        if excluded:
            tags.append('excluded')
        tree.item(item_id, tags=tags)
        if excluded:
            self.log("선택한 거래를 예산 합계에서 제외했습니다")
        else:
            self.log("선택한 거래를 예산 합계에 다시 포함했습니다")

    def refresh_analysis_views(self, update_transactions=True):
        """제외 설정을 반영해 거래 목록, 집계, 예산 요약 갱신"""
        included_df = self.all_transactions_df[
            ~self.all_transactions_df['budget_excluded']
        ].copy()

        self.transactions_df = self.all_transactions_df[
            ['date', 'amount', 'merchant', 'budget_excluded']
        ].copy()
        self.transactions_df.columns = ['날짜', '금액', '가맹점', '예산 제외']
        self.transactions_df['날짜'] = self.transactions_df['날짜'].dt.strftime('%Y-%m-%d %H:%M')
        self.transactions_df['예산 제외'] = self.transactions_df['예산 제외'].map(
            {True: '예', False: '아니오'}
        )

        self.daily_df = included_df.groupby(included_df['date'].dt.date).agg({
            'amount': ['sum', 'count']
        }).reset_index()
        self.daily_df.columns = ['날짜', '금액', '건수']
        self.daily_df['누적금액'] = self.daily_df['금액'].cumsum()

        self.monthly_df = included_df.groupby(included_df['date'].dt.to_period('M')).agg({
            'amount': ['sum', 'count']
        }).reset_index()
        self.monthly_df.columns = ['월', '금액', '건수']
        self.monthly_df['누적금액'] = self.monthly_df['금액'].cumsum()

        self.quarterly_df = included_df.groupby(included_df['date'].dt.to_period('Q')).agg({
            'amount': ['sum', 'count']
        }).reset_index()
        self.quarterly_df.columns = ['분기', '금액', '건수']
        self.quarterly_df['누적금액'] = self.quarterly_df['금액'].cumsum()

        self.yearly_df = included_df.groupby(included_df['date'].dt.year).agg({
            'amount': ['sum', 'count']
        }).reset_index()
        self.yearly_df.columns = ['연도', '금액', '건수']
        self.yearly_df['누적금액'] = self.yearly_df['금액'].cumsum()

        if update_transactions:
            self.update_transactions_treeview()
        self.update_treeview(self.daily_tab.tree, self.daily_df)
        self.update_treeview(self.monthly_tab.tree, self.monthly_df)
        self.update_treeview(self.quarterly_tab.tree, self.quarterly_df)
        self.update_treeview(self.yearly_tab.tree, self.yearly_df)
        self.update_budget_summary(included_df)

    def update_budget_summary(self, included_df):
        """올해 예산에 포함된 거래만으로 상단 소비 요약 갱신"""
        current_year = datetime.now().year
        this_year_df = included_df[included_df['date'].dt.year == current_year]

        total_amount = this_year_df['amount'].sum()
        krw_amount = this_year_df[this_year_df['currency'] == 'KRW']['amount'].sum()
        if 'original_amount' in this_year_df.columns:
            usd_amount = this_year_df.loc[
                this_year_df['currency'] == 'USD', 'original_amount'
            ].sum()
        else:
            usd_amount = 0
        months = this_year_df['date'].dt.to_period('M').nunique()
        this_month_amount = this_year_df.loc[
            this_year_df['date'].dt.month == datetime.now().month, 'amount'
        ].sum()

        try:
            yearly_budget = int(self.budget_entry.get().replace(',', ''))
            phone_number = self.phone_entry.get()

            self.config['yearly_budget'] = yearly_budget
            self.config['phone_number'] = phone_number
            save_config(self.config)

            remaining = yearly_budget - total_amount
            self.budget_ratio = total_amount / yearly_budget if yearly_budget > 0 else 0.0
            percent_text = f"{self.budget_ratio * 100:.1f}%" if yearly_budget > 0 else "-"
            budget_text = f"{total_amount:,}원 사용 · 예산 {yearly_budget:,}원"
            if remaining >= 0:
                remaining_text = f"{remaining:,}원 남음"
            else:
                remaining_text = f"{-remaining:,}원 초과"
        except ValueError:
            self.budget_ratio = 0.0
            percent_text = "-"
            budget_text = f"{total_amount:,}원 사용"
            remaining_text = "연간 예산을 입력해주세요"

        avg_monthly = total_amount / months if months > 0 else 0
        excluded_count = int(
            self.all_transactions_df.loc[
                self.all_transactions_df['date'].dt.year == current_year,
                'budget_excluded',
            ].sum()
        )
        if excluded_count:
            budget_text += f" · 예산 제외 {excluded_count}건"
        self.percent_label.config(text=percent_text)
        self.remaining_label.config(text=remaining_text)
        self.total_label.config(text=budget_text)
        self.draw_progress()

        self.month_label.config(text=f"{this_month_amount:,.0f}원")
        self.avg_label.config(text=f"{avg_monthly:,.0f}원")
        self.krw_label.config(text=f"{krw_amount:,.0f}원")
        self.usd_label.config(text=f"${usd_amount:,.2f}")

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
            conn = connect_messages_db()

            self.log(f"전화번호 {phone_number}의 메시지 검색 중...")
            messages = pd.read_sql_query("""
                SELECT m.ROWID AS message_id, m.*
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
                date = pd.Timestamp(datetime.fromtimestamp(timestamp))

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
                        'text': text,
                        'transaction_key': f"message:{messages.iloc[i]['message_id']}"
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
                        'text': text,
                        'transaction_key': f"message:{messages.iloc[i]['message_id']}"
                    })
                    continue

                # 해외 결제 금액 추출 (USD, EUR 등)
                foreign_match = re.search(r'([\d,]+\.?\d*)\((KRW|USD|EUR|JPY|CNY|GBP)\)', text)
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
                    'manual': True,
                    'transaction_key': f"manual:{manual['id']}"
                })

            if not data:
                messagebox.showwarning("경고", "금액 정보가 포함된 메시지를 찾을 수 없습니다")
                self.log("금액 정보를 찾을 수 없습니다")
                return

            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            df['budget_excluded'] = df['transaction_key'].isin(
                self.excluded_transaction_keys
            )
            self.all_transactions_df = df

            # 제외 설정을 반영한 Treeview와 집계 갱신
            self.log("결과를 표시하는 중...")
            self.refresh_analysis_views()

            # CSV 내보내기 버튼 활성화
            self.export_btn.config(state='normal')

            excluded_count = int(df['budget_excluded'].sum())
            self.log(
                f"완료! 총 {len(data)}건 분석, 예산 합계 제외 {excluded_count}건"
            )

        except Exception as e:
            self.log(f"오류 발생: {str(e)}")
            if is_messages_access_error(e):
                self.log("메시지 접근 권한이 필요합니다. 설정에서 전체 디스크 접근을 허용하세요")
                prompt_full_disk_access()
            else:
                messagebox.showerror("오류", f"오류가 발생했습니다:\n{str(e)}")

        finally:
            self.analyze_btn.config(state='normal')
            if 'conn' in locals() and conn is not None:
                close_messages_db(conn)

    def add_manual_transaction_dialog(self):
        """수동 거래 추가 다이얼로그"""
        dialog = tk.Toplevel(self.root)
        dialog.title("거래 수동 추가")
        dialog.geometry("420x280")
        dialog.configure(bg=COLORS['bg'])

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

        ttk.Button(button_frame, text="추가", style='Accent.TButton', command=save_transaction).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(button_frame, text="취소", style='Secondary.TButton', command=dialog.destroy).pack(side=tk.RIGHT)

    def manage_manual_transactions_dialog(self):
        """수동 거래 관리 다이얼로그"""
        dialog = tk.Toplevel(self.root)
        dialog.title("수동 거래 관리")
        dialog.geometry("600x420")
        dialog.configure(bg=COLORS['bg'])

        # 리스트박스와 스크롤바
        frame = ttk.Frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        listbox = tk.Listbox(
            frame, yscrollcommand=scrollbar.set, font=self.font(13),
            bg=COLORS['bg'], fg=COLORS['text'], relief='flat', borderwidth=0,
            highlightthickness=1, highlightbackground=COLORS['line'],
            highlightcolor=COLORS['line'], selectbackground=COLORS['accent_soft'],
            selectforeground=COLORS['text'], activestyle='none',
        )
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)

        # 수동 거래 내역 로드
        def load_transactions():
            listbox.delete(0, tk.END)
            transactions = load_manual_transactions()
            for i, trans in enumerate(transactions):
                date = trans['date'][:10] if len(trans['date']) > 10 else trans['date']
                text = f"{date} | {trans['amount']:,}원 | {trans['merchant']}"
                listbox.insert(tk.END, text)

        load_transactions()

        # 삭제 기능
        def delete_selected():
            selection = listbox.curselection()
            if not selection:
                messagebox.showwarning("경고", "삭제할 항목을 선택해주세요")
                return

            index = selection[0]
            transactions = load_manual_transactions()
            if 0 <= index < len(transactions):
                merchant = transactions[index]['merchant']
                if messagebox.askyesno("확인", f"{merchant} 거래를 삭제하시겠습니까?"):
                    if delete_manual_transaction(index):
                        load_transactions()
                        # 자동으로 다시 분석
                        self.analyze_messages()
                        messagebox.showinfo("완료", "거래가 삭제되었습니다")
                    else:
                        messagebox.showerror("오류", "삭제에 실패했습니다")

        # 버튼 프레임
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill=tk.X, padx=20, pady=10)

        ttk.Button(button_frame, text="닫기", style='Secondary.TButton', command=dialog.destroy).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(button_frame, text="삭제", style='Secondary.TButton', command=delete_selected).pack(side=tk.RIGHT)

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

def use_cardman_dock_name():
    """Dock에 python3.13 대신 카드맨 이름을 보여 준다. tk.Tk()보다 먼저 불러야 한다."""
    try:
        from AppKit import NSBundle
    except ImportError:
        return
    info = NSBundle.mainBundle().infoDictionary()
    if info is not None:
        info["CFBundleName"] = "카드맨"


def use_cardman_dock_icon():
    """Dock 아이콘을 카드맨으로 바꾼다. Tk가 NSApplication을 만든 뒤에 불러야 한다."""
    try:
        from AppKit import NSApplication, NSImage
    except ImportError:
        return
    icon_path = Path(__file__).parent / "CardMan.icns"
    if icon_path.exists():
        icon = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
        if icon is not None:
            NSApplication.sharedApplication().setApplicationIconImage_(icon)


if __name__ == "__main__":
    ensure_menubar_running()
    use_cardman_dock_name()
    root = tk.Tk()
    use_cardman_dock_icon()
    app = MessageAnalyzerApp(root)
    root.mainloop()
