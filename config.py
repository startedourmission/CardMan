import json
from pathlib import Path

CONFIG_FILE = Path.home() / ".cardman_config.json"
MANUAL_TRANSACTIONS_FILE = Path.home() / ".cardman_manual_transactions.json"

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
                return json.load(f)
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
        'date': date_str,
        'amount': amount,
        'merchant': merchant,
        'currency': currency,
        'manual': True
    }

    transactions.append(new_transaction)
    return save_manual_transactions(transactions)
