import os
import json
import shutil
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from google_sheets import connect_sheet

PREMIUM_FILE = "premium_settings.json"
SAMPLE_FOLDER = "diary_data/sample"

SHEET_NAME = "DiaryUserData"
DIARY_SHEET = "UserDiaries"
DIARY_LOG_SHEET = "PremiumDiarySamples"

# ✅ 有料ユーザーの設定を取得
def get_premium_settings(user_id):
    if not os.path.exists(PREMIUM_FILE):
        return {}
    with open(PREMIUM_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get(user_id, {})

# ✅ プレミアム設定をプロンプトに反映
def apply_premium_to_prompt(premium, base_prompt, diary_samples=None):
    parts = []

    if premium.get("emoji_list"):
        parts.append(f"【使用したい絵文字】\n{premium['emoji_list']}")
    if premium.get("tone_tags"):
        parts.append(f"【日記のテイスト】\n{premium['tone_tags']}")
    if premium.get("ng_elements"):
        parts.append(f"【NGワード・避けたい要素】\n{premium['ng_elements']}")
    if premium.get("appeal_tags"):
        parts.append(f"【指名につながりやすい特徴】\n{premium['appeal_tags']}")
    if premium.get("appeal_elements"):
        parts.append(f"【推しポイント・演出したい雰囲気】\n{premium['appeal_elements']}")
    if premium.get("weekly_schedule"):
        parts.append(f"【出勤の曜日・時間帯】\n{premium['weekly_schedule']}")
    if premium.get("fav_words"):
        parts.append(f"【よく使う言葉・口癖】\n{premium['fav_words']}")

    if diary_samples:
        sample_block = "\n---\n".join(diary_samples)
        parts.append(f"【文章スタイル参考】\n以下はこのユーザーが実際に書いた写メ日記の例です。\n\n{sample_block}")

    addon = "\n\n".join(parts)
    return f"{base_prompt}\n\n【プレミアム情報・構成ガイド】\n{addon}" if parts else base_prompt

# ✅ 👍フィードバック削除（有料化時）
def clean_feedback_on_upgrade(user_id):
    feedback_dir = os.path.join("feedback", "good", user_id)
    if os.path.exists(feedback_dir):
        shutil.rmtree(feedback_dir)

# ✅ サンプル日記取得（無料ユーザー用）
def get_sample_diary_entries(diary_type):
    filepath = os.path.join(SAMPLE_FOLDER, f"{diary_type}.txt")
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()][:10]

# ✅ [旧関数] 提出された日記をUserDiariesシートに保存
def save_user_diary_entry(user_id, diary_type, diary_text):
    sheet = connect_sheet(SHEET_NAME, DIARY_SHEET)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([user_id, diary_type, now, diary_text])

# ✅ [新] 提出日記をまとめてUserDiaryLogに保存
def save_diary_entries_to_sheet(user_id, raw_text):
    sheet = connect_sheet(SHEET_NAME, DIARY_LOG_SHEET)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entries = [entry.strip() for entry in raw_text.strip().split("\n\n") if entry.strip()]

    for entry in entries:
        lower = entry.lower()
        if any(word in lower for word in ["出勤", "おはよう", "今日も頑張る"]):
            diary_type = "shukkin"
        elif any(word in lower for word in ["退勤", "おやすみ", "ありがとう", "今日も"]):
            diary_type = "taikin"
        elif any(word in lower for word in ["ありがとう", "感謝", "差し入れ"]):
            diary_type = "orei"
        else:
            diary_type = "unknown"

        sheet.append_row([user_id, diary_type, entry, now])

# ✅ [新] Google Sheetsから有料ユーザーの自作日記を取得
def get_user_diary_samples(user_id, diary_type, limit=10):
    sheet = connect_sheet(SHEET_NAME, DIARY_LOG_SHEET)
    records = sheet.get_all_records()
    filtered = [
        row["diary_text"] for row in records
        if row.get("user_id") == user_id and row.get("diary_type") == diary_type
    ]
    return filtered[-limit:]  # 新しい順に最大10件

# ✅ 使用された日記の使用回数を+1する
def increment_diary_usage(user_id, diary_text):
    sheet = connect_sheet("DiaryUserData", "PremiumDiarySamples")
    records = sheet.get_all_records()

    for idx, row in enumerate(records):
        if row["user_id"] == user_id and row["diary_text"].strip() == diary_text.strip():
            current = row.get("used_count", 0)
            new_count = int(current) + 1 if str(current).isdigit() else 1
            sheet.update_cell(idx + 2, 5, new_count)  # 5列目が used_count の列
            break

