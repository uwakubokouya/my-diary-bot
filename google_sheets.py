import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# 🔧 汎用：指定スプレッドシート・タブへ接続
def connect_sheet(spreadsheet_name, worksheet_name):
    creds = Credentials.from_service_account_file('/etc/secrets/credentials.json', scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open(spreadsheet_name).worksheet(worksheet_name)

# ---------------------------
# ① 有料プラン申請管理 (user_requests)
# ---------------------------
def append_user_to_sheet(user_id, nickname="未設定", status="未承認", store="店舗未設定"):
    sheet = connect_sheet("DiaryUserData", "user_requests")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_row = [user_id, status, now, nickname, store]

    records = sheet.get_all_records()
    if any(row["user_id"] == user_id for row in records):
        return

    sheet.append_row(new_row)

def get_approved_users():
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    records = sheet.get_all_records()
    return [row["user_id"] for row in records if row.get("ステータス") == "承認済"]

def complete_premium_registration(user_id, nickname, store):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    records = sheet.get_all_records()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for idx, row in enumerate(records):
        if row["user_id"] == user_id:
            sheet.update_cell(idx + 2, 7, "承認待ち")
            sheet.update_cell(idx + 2, 8, now)
            sheet.update_cell(idx + 2, 9, store)
            return

# ---------------------------
# ② ユーザー登録情報管理
# ---------------------------
def register_user_info(user_id, name, age_range, tone):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    records = sheet.get_all_records()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for idx, row in enumerate(records):
        if row["user_id"] == user_id:
            sheet.update_cell(idx + 2, 2, name)
            sheet.update_cell(idx + 2, 3, age_range)
            sheet.update_cell(idx + 2, 4, tone)
            sheet.update_cell(idx + 2, 5, now)
            return

    sheet.append_row([user_id, name, age_range, tone, now])

def save_user_info_to_sheet(user_id, info):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    records = sheet.get_all_records()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for idx, row in enumerate(records):
        if row["user_id"] == user_id:
            sheet.update(f"A{idx + 2}:E{idx + 2}", [[
                user_id,
                info.get("name", ""),
                info.get("age_range", ""),
                info.get("tone", ""),
                now
            ]])
            return

    sheet.append_row([
        user_id,
        info.get("name", ""),
        info.get("age_range", ""),
        info.get("tone", ""),
        now
    ])

# ---------------------------
# ③ 使用回数ログ管理
# ---------------------------
def log_usage(user_id):
    sheet = connect_sheet("DiaryUserData", "UsageLog")
    today = datetime.now().strftime("%Y-%m-%d")
    records = sheet.get_all_records()

    for i, row in enumerate(records):
        if row["user_id"] == user_id and row["date"] == today:
            sheet.update_cell(i + 2, 3, int(row["count"]) + 1)
            return

    sheet.append_row([user_id, today, 1])

def get_usage_count(user_id):
    sheet = connect_sheet("DiaryUserData", "UsageLog")
    today = datetime.now().strftime("%Y-%m-%d")
    records = sheet.get_all_records()

    for row in records:
        if row["user_id"] == user_id and row["date"] == today:
            return int(row["count"])
    return 0

# ---------------------------
# ④ フィードバックログ管理
# ---------------------------
def log_feedback(user_id, diary_type, result, diary_text):
    sheet = connect_sheet("DiaryUserData", "FeedbackLog")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([user_id, diary_type, result, now, diary_text])

def get_positive_feedback(user_id, diary_type=None, limit=5):
    sheet = connect_sheet("DiaryUserData", "FeedbackLog")
    records = sheet.get_all_records()
    filtered = [
        row for row in records
        if row["user_id"] == user_id and row["result"] == "good"
        and (diary_type is None or row["diary_type"] == diary_type)
    ]
    filtered = sorted(filtered, key=lambda x: x["timestamp"], reverse=True)
    return [row["diary_text"] for row in filtered[:limit]]

def append_diary_sample_to_sheet(user_id, diary_type, diary_text, timestamp):
    sheet = connect_sheet("DiaryUserData", "PremiumDiarySamples")
    sheet.append_row([user_id, diary_type, timestamp, diary_text])

# ---------------------------
# ⑤ 有料ユーザーの自作日記
# ---------------------------
def get_premium_diary_samples(user_id, diary_type, limit=10):
    sheet = connect_sheet("DiaryUserData", "PremiumDiarySamples")
    records = sheet.get_all_records()
    samples = [
        row["diary_text"].strip()
        for row in records
        if row["user_id"] == user_id and row["diary_type"] == diary_type and row.get("diary_text")
    ]
    return samples[:limit]

# ---------------------------
# ⑥ ユーザー提出日記の保存
# ---------------------------
def save_user_diary_entry(user_id, diary_type, diary_text):
    sheet = connect_sheet("DiaryUserData", "UserDiaries")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([user_id, diary_type, diary_text, now], value_input_option="USER_ENTERED")

def get_user_diary_samples_from_sheet(user_id, diary_type=None, limit=10):
    sheet = connect_sheet("DiaryUserData", "UserDiaries")
    records = sheet.get_all_records()
    filtered = [
        row for row in records
        if row["user_id"] == user_id and (diary_type is None or row["diary_type"] == diary_type)
    ]
    sorted_entries = sorted(filtered, key=lambda x: x["created_at"], reverse=True)
    return [row["diary_text"] for row in sorted_entries[:limit]]

# ---------------------------
# ⑦ テンプレート取得・使用カウント
# ---------------------------
def get_templates_by_section(sheet_name, tab_name):
    sheet = connect_sheet(sheet_name, tab_name)
    data = sheet.get_all_records()
    templates = {}
    for row in data:
        section = row["section"].strip()
        content = row["text"].strip()
        templates.setdefault(section, []).append(content)
    return templates

def increment_template_usage(sheet, section, text, records):
    header = sheet.row_values(1)
    count_col = header.index("used_count") + 1
    for i, row in enumerate(records):
        if row["section"].strip() == section and row["text"].strip() == text.strip():
            current = row.get("used_count", 0)
            count = int(current) if str(current).isdigit() else 0
            sheet.update_cell(i + 2, count_col, count + 1)
            break

# ---------------------------
# ⑧ テストユーザー
# ---------------------------
def get_test_users():
    sheet = connect_sheet("DiaryUserData", "TestUserList")
    return [row["user_id"] for row in sheet.get_all_records() if row.get("user_id")]

def is_test_user(user_id):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    for row in sheet.get_all_records():
        if row.get("user_id") == user_id:
            return str(row.get("is_test_user", "")).strip().upper() == "TRUE"
    return False

# ---------------------------
# ⑨ その他補助関数
# ---------------------------
def get_user_info(user_id):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    for row in sheet.get_all_records():
        if row.get("user_id") == user_id:
            return row
    return {}

def get_user_info(user_id):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    records = sheet.get_all_records()
    for row in records:
        if str(row.get("user_id", "")).strip() == str(user_id):
            return {
                "user_id": user_id,
                "name": row.get("源氏名", ""),  # ←ここが必要！
                "age_range": row.get("年代", ""),
                "tone": row.get("口調", ""),
                "is_premium": row.get("ステータス", "") == "承認済"
            }
    return None

# ✅ 追加：PremiumUserInfo タブからプレミアム情報を取得する関数
def get_premium_user_info(user_id):
    sheet = connect_sheet("DiaryUserData", "PremiumUserInfo")
    records = sheet.get_all_records()

    for row in records:
        if str(row.get("user_id", "")).strip() == str(user_id).strip():
            return {
                "emoji_list": row.get("emoji_list", ""),
                "tone_tags": row.get("tone_tags", ""),
                "ng_elements": row.get("ng_elements", ""),
                "appeal_tags": row.get("appeal_tags", ""),
                "appeal_elements": row.get("appeal_elements", ""),
                "weekly_schedule": row.get("weekly_schedule", ""),
                "fav_words": row.get("fav_words", ""),
                "other_requests": row.get("other_requests", "")
            }
    return None
    
# ✅ LINEユーザーIDから基本情報を取得（name, age_range, tone のみ）
def get_user_info_from_sheet(user_id):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    records = sheet.get_all_records()
    for row in records:
        if str(row.get("user_id", "")).strip() == str(user_id):
            return {
                "name": row.get("源氏名", ""),
                "age_range": row.get("年代", ""),
                "tone": row.get("口調", "")
            }
    return {}

def update_premium_status(user_id, status):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for idx, row in enumerate(sheet.get_all_records()):
        if row["user_id"] == user_id:
            sheet.update_cell(idx + 2, 7, status)
            sheet.update_cell(idx + 2, 8, now)
            return

def mark_premium_notified(user_id):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    for idx, row in enumerate(sheet.get_all_records()):
        if row["user_id"] == user_id:
            sheet.update_cell(idx + 2, 10, "TRUE")
            return

def get_newly_approved_users():
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    return [
        row for row in sheet.get_all_records()
        if row.get("ステータス") == "承認済" and str(row.get("通知済み", "")).strip().upper() != "TRUE"
    ]

def append_user_diary_entry(user_id, diary_type, diary_text):
    sheet = connect_sheet("DiaryUserData", "UserDiaryLog")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([user_id, diary_type, diary_text, now])
