import os
import json
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
    "name": "① 自分の呼び方を教えてね♪（日記で自分の名前を書く時の表現だよ）",
    "age_range": "② お店での設定年齢（プロフィール上の年齢）を教えてね♪",
    "tone": (
        "③ 自分のキャラの雰囲気を番号で一つ選んでね♪（口調のスタイル）\n"
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

# ✅ 環境変数から読み込み（Renderではこれが推奨）
service_account_info = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
client = gspread.authorize(creds)

# ✅ シート設定
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

    # 入力バリデーション（tone選択肢）
    if current_key == "tone":
        if message_text not in TONE_OPTIONS:
            return "番号を1〜15の中から選んでね♪"
        registering_users[user_id]["data"][current_key] = TONE_OPTIONS[message_text]
    else:
        registering_users[user_id]["data"][current_key] = message_text

    step += 1
    if step < len(REGISTER_STEPS):
        next_key = REGISTER_STEPS[step]
        registering_users[user_id]["step"] = step
        return REGISTER_QUESTIONS[next_key]
    else:
        # 全ステップ完了！保存処理
        user_data = registering_users[user_id]["data"]

        # JSONにも保存
        try:
            with open("users_info.json", "r", encoding="utf-8") as f:
                all_users = json.load(f)
        except FileNotFoundError:
            all_users = {}
        all_users[user_id] = user_data
        with open("users_info.json", "w", encoding="utf-8") as f:
            json.dump(all_users, f, indent=2, ensure_ascii=False)

        # ✅ スプレッドシートにも保存
        save_user_info_to_sheet(user_id, user_data)

        # ✅ 登録後キャッシュ更新（これを追加）
        refresh_user_info_cache(user_id)

        # 登録完了後、仮データ削除
        del registering_users[user_id]
        return "🎉 登録が完了しました！日記リクエストを送ってみてください♪"

# ✅ ユーザー情報取得（キャッシュあり版）
def get_user_info(user_id):
    if user_id in user_info_cache:
        return user_info_cache[user_id]

    # シートから取得
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
        
        # ✅ キャッシュを強制的に更新する関数
def refresh_user_info_cache(user_id):
    if user_id in user_info_cache:
        del user_info_cache[user_id]
    get_user_info(user_id)


    return None
