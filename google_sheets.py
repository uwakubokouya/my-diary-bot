import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# 🔧 汎用：指定スプレッドシート・タブへ接続
def connect_sheet(spreadsheet_name, worksheet_name):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
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

# ✅ プレミアム登録完了ユーザーの登録
def complete_premium_registration(user_id, nickname, store):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    records = sheet.get_all_records()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for idx, row in enumerate(records):
        if row["user_id"] == user_id:
            sheet.update_cell(idx + 2, 7, "承認待ち")  # G列: ステータス
            sheet.update_cell(idx + 2, 8, now)         # H列: 登録日時
            sheet.update_cell(idx + 2, 9, store)       # I列: 店舗名
            return

# ---------------------------
# ② ユーザー登録情報管理 (UserInfoLog)
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

    new_row = [user_id, name, age_range, tone, now]
    sheet.append_row(new_row)

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
# ③ 使用回数ログ管理 (UsageLog)
# ---------------------------
def log_usage(user_id):
    sheet = connect_sheet("DiaryUserData", "UsageLog")
    today = datetime.now().strftime("%Y-%m-%d")
    records = sheet.get_all_records()

    for i, row in enumerate(records):
        if row["user_id"] == user_id and row["date"] == today:
            count = int(row["count"]) + 1
            sheet.update_cell(i + 2, 3, count)
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
# ④ フィードバックログ管理 (FeedbackLog)
# ---------------------------
def log_feedback(user_id, diary_type, result, diary_text):
    sheet = connect_sheet("DiaryUserData", "FeedbackLog")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_row = [user_id, diary_type, result, now, diary_text]
    sheet.append_row(new_row)

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

def append_diary_sample_to_sheet(user_id, diary_type, content, timestamp):
    sheet = connect_sheet("DiaryUserData", "PremiumDiarySamples")
    sheet.append_row([user_id, diary_type, content, timestamp])

# ---------------------------
# ✅ 有料ユーザーの自作日記取得（PremiumDiarySamplesから）
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
# ⑤ ユーザー提出日記の保存（UserDiariesシート）
# ---------------------------
def save_user_diary_entry(user_id, diary_type, diary_text):
    sheet = connect_sheet("DiaryUserData", "UserDiaries")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_row = [user_id, diary_type, diary_text, now]
    sheet.append_row(new_row, value_input_option="USER_ENTERED")

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
# ✅ テンプレート取得（各タブ）
# ---------------------------
def get_templates_by_section(sheet_name, tab_name):
    sheet = connect_sheet(sheet_name, tab_name)
    data = sheet.get_all_records()

    templates = {}
    for row in data:
        section = row["section"].strip()
        content = row["text"].strip()
        if section not in templates:
            templates[section] = []
        templates[section].append(content)
    return templates

# ---------------------------
# ✅ テンプレ使用回数の記録（修正版）
# ---------------------------
def increment_template_usage(sheet, section, text, records):
    header = sheet.row_values(1)
    section_col = header.index("section") + 1
    text_col = header.index("text") + 1
    count_col = header.index("used_count") + 1

    for i, row in enumerate(records):
        if row["section"].strip() == section and row["text"].strip() == text.strip():
            current_count = row.get("used_count", 0)
            if current_count == "":
                current_count = 0
            elif isinstance(current_count, str) and current_count.isdigit():
                current_count = int(current_count)
            elif isinstance(current_count, int):
                current_count = current_count
            else:
                current_count = 0

            sheet.update_cell(i + 2, count_col, current_count + 1)
            break

# ---------------------------
# ✅ テストユーザー一覧の取得（使用制限スキップ用）
# ---------------------------
def get_test_users():
    sheet = connect_sheet("DiaryUserData", "TestUserList")
    records = sheet.get_all_records()
    return [row["user_id"] for row in records if row.get("user_id")]

def is_test_user(user_id):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    records = sheet.get_all_records()
    for row in records:
        if row.get("user_id") == user_id:
            return str(row.get("is_test_user", "")).strip().upper() == "TRUE"
    return False

def get_user_info(user_id):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    rows = sheet.get_all_records()
    for row in rows:
        if row.get("user_id") == user_id:
            return row
    return {}

def get_user_info_from_sheet(user_id):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    records = sheet.get_all_records()
    for row in records:
        if row["user_id"] == user_id:
            return {
                "name": row.get("name", ""),
                "age_range": row.get("age_range", ""),
                "tone": row.get("tone", "")
            }
    return {}

def append_diary_sample_to_sheet(user_id, diary_type, diary_text, timestamp):
    sheet = connect_sheet("DiaryUserData", "PremiumDiarySamples")
    new_row = [user_id, diary_type, timestamp, diary_text]
    sheet.append_row(new_row)

def update_premium_status(user_id, status):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    records = sheet.get_all_records()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for idx, row in enumerate(records):
        if row["user_id"] == user_id:
            sheet.update_cell(idx + 2, 7, status)
            sheet.update_cell(idx + 2, 8, now)
            return

def mark_premium_notified(user_id):
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    records = sheet.get_all_records()

    for idx, row in enumerate(records):
        if row["user_id"] == user_id:
            sheet.update_cell(idx + 2, 10, "TRUE")
            return

def get_newly_approved_users():
    sheet = connect_sheet("DiaryUserData", "UserInfoLog")
    records = sheet.get_all_records()
    return [
        row for row in records
        if row.get("ステータス", "") == "承認済"
        and str(row.get("通知済み", "")).strip().upper() != "TRUE"
    ]

def append_user_diary_entry(user_id, diary_type, diary_text):
    sheet = connect_sheet("DiaryUserData", "UserDiaryLog")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([user_id, diary_type, diary_text, now])
