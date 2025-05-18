import os 
import gspread
from google.oauth2.service_account import Credentials
from google_sheets import save_user_info_to_sheet

# ✅ 口調（tone）番号と名称対応
TONE_OPTIONS = {
    "1": "甘えんぼ系",
    "2": "ギャル系",
    "3": "大人っぽ系",
    "4": "ロリ系・妹系",
    "5": "サバサバ系",
    "6": "丁寧系",
    "7": "しっかり真面目系",
    "8": "ふんわり癒し系",
    "9": "学園系・初心者風",
    "10": "お姉さん系",
    "11": "かっこいい系",
    "12": "エステ・スパ風",
    "13": "ドM系",
    "14": "清楚系",
    "15": "方言系（関西）"
}

# ✅ 登録時のステップ定義
REGISTER_STEPS = ["name", "age_range", "tone"]
REGISTER_QUESTIONS = {
    "name": "登録を開始します♪\n① まずは自分の呼び方を教えてね♪（日記で自分の名前を書く時の表現だよ）",
    "age_range": "② 次にお店での設定年齢（プロフィール上の年齢）を教えてね♪",
    "tone": (
        "③ 最後に自分のキャラの雰囲気を番号で一つ選んでね♪（口調のスタイル）\n"
        + "\n".join([f"{num}. {label}" for num, label in TONE_OPTIONS.items()])
    )
}

# ✅ 登録中のユーザー管理用
registering_users = {}

# ✅ ユーザー情報キャッシュ
user_info_cache = {}

# ✅ Google Sheets 認証情報
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
creds = Credentials.from_service_account_file('/etc/secrets/credentials.json', scopes=SCOPES)
client = gspread.authorize(creds)

SHEET_NAME = "DiaryUserData"
TAB_NAME = "UserInfoLog"

# ✅ 登録中か判定する関数
def is_registering(user_id):
    return user_id in registering_users

# ✅ 登録ステップを進める関数
def handle_registration_step(user_id, message_text):
    if user_id not in registering_users:
        registering_users[user_id] = {"step": 0, "data": {}}
        return REGISTER_QUESTIONS[REGISTER_STEPS[0]]

    step = registering_users[user_id]["step"]
    current_key = REGISTER_STEPS[step]

    if current_key == "tone":
        if message_text not in TONE_OPTIONS:
            return "番号を1〜15の中から一つ選んでね♪"
        registering_users[user_id]["data"][current_key] = TONE_OPTIONS[message_text]
    else:
        registering_users[user_id]["data"][current_key] = message_text

    step += 1
    if step < len(REGISTER_STEPS):
        next_key = REGISTER_STEPS[step]
        registering_users[user_id]["step"] = step
        return REGISTER_QUESTIONS[next_key]
    else:
        user_data = registering_users[user_id]["data"]

        save_user_info_to_sheet(user_id, user_data)
        refresh_user_info_cache(user_id)
        del registering_users[user_id]

        return (
            "🎉 以下の情報で登録が完了しました！\n\n"
            f"▶️ 名前：{user_data['name']}\n"
            f"▶️ 年齢：{user_data['age_range']}\n"
            f"▶️ キャラ：{user_data['tone']}\n\n"
            "このままでよければ、日記リクエスト【出勤】【退勤】【お礼】のいずれかを送ってみてください♪\n"
            "変更したい場合は、もう一度「情報を登録する」と送ってね😊"
        )

# ✅ ユーザー情報取得

def get_user_info(user_id):
    if user_id in user_info_cache:
        return user_info_cache[user_id]

    sheet = client.open(SHEET_NAME).worksheet(TAB_NAME)
    data = sheet.get_all_records()

    for row in data:
        if str(row.get("user_id", "")).strip() == str(user_id).strip():
            user_info = {
                "user_id": row.get("user_id"),
                "name": row.get("源氏名"),
                "age_range": row.get("年代"),
                "tone": row.get("口調"),
                "is_premium": row.get("is_premium", False)
            }
            user_info_cache[user_id] = user_info
            return user_info
    return None

# ✅ キャッシュを更新

def refresh_user_info_cache(user_id):
    if user_id in user_info_cache:
        del user_info_cache[user_id]
    get_user_info(user_id)
