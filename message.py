def decode_message(row):
    msg_text = row['text']
    msg_attributed_body = row['attributedBody']

    # Logic from https://github.com/my-other-github-account/imessage_tools
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

import sqlite3
import pandas as pd
import re
from datetime import datetime
from pathlib import Path

path = Path.home() / "Library" / "Messages" / "chat.db"

conn = sqlite3.connect(path)
# connect to the database
phone_number = "+8215881688"  # 원하는 전화번호로 변경
messages = pd.read_sql_query("""
    SELECT m.*
    FROM message m
    JOIN handle h ON m.handle_id = h.ROWID
    WHERE h.id = ?
    ORDER BY m.date ASC

""", conn, params=[phone_number])
# 메시지 디코딩 및 금액 추출
data = []
for i in range(len(messages)):
    text = decode_message(messages.iloc[i])

    # 금액 추출 (예: "10,000원", "5000원" 등)
    amount_match = re.search(r'([\d,]+)원', text)
    if amount_match:
        amount = int(amount_match.group(1).replace(',', ''))

        # iMessage date는 2001-01-01 00:00:00 UTC 기준 나노초
        timestamp = messages.iloc[i]['date'] / 1_000_000_000 + 978307200  # Unix timestamp로 변환
        date = pd.to_datetime(timestamp, unit='s')

        data.append({
            'date': date,
            'amount': amount,
            'text': text
        })

df = pd.DataFrame(data)

if not df.empty:
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')

    # 일별 집계
    daily = df.groupby(df['date'].dt.date).agg({
        'amount': ['sum', 'count']
    }).reset_index()
    daily.columns = ['날짜', '금액', '건수']
    daily['누적금액'] = daily['금액'].cumsum()

    # 월별 집계
    monthly = df.groupby(df['date'].dt.to_period('M')).agg({
        'amount': ['sum', 'count']
    }).reset_index()
    monthly.columns = ['월', '금액', '건수']
    monthly['누적금액'] = monthly['금액'].cumsum()

    # 분기별 집계
    quarterly = df.groupby(df['date'].dt.to_period('Q')).agg({
        'amount': ['sum', 'count']
    }).reset_index()
    quarterly.columns = ['분기', '금액', '건수']
    quarterly['누적금액'] = quarterly['금액'].cumsum()

    # 연도별 집계
    yearly = df.groupby(df['date'].dt.year).agg({
        'amount': ['sum', 'count']
    }).reset_index()
    yearly.columns = ['연도', '금액', '건수']
    yearly['누적금액'] = yearly['금액'].cumsum()

    print("=== 일별 집계 ===")
    print(daily)
    print("\n=== 월별 집계 ===")
    print(monthly)
    print("\n=== 분기별 집계 ===")
    print(quarterly)
    print("\n=== 연도별 집계 ===")
    print(yearly)

    # CSV로 저장
    daily.to_csv('daily.csv', index=False, encoding='utf-8-sig')
    monthly.to_csv('monthly.csv', index=False, encoding='utf-8-sig')
    quarterly.to_csv('quarterly.csv', index=False, encoding='utf-8-sig')
    yearly.to_csv('yearly.csv', index=False, encoding='utf-8-sig')
    print("\nCSV 파일 저장 완료: daily.csv, monthly.csv, quarterly.csv, yearly.csv")
else:
    print("금액 정보가 포함된 메시지를 찾을 수 없습니다.")