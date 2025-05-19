import os
import json
import datetime
from google_sheets import (
    connect_sheet,
    complete_premium_registration,
    append_diary_sample_to_sheet,
    save_premium_user_info_to_sheet,  # ✅ 追加
    get_user_info_from_sheet
)

# ✅ プレミアム設定保存ファイル
PREMIUM_FILE = "premium_settings.json"

# ✅ プレミアム設定キャッシュ
premium_settings_cache = {}

# ✅ 登録中プレミアム設定の仮状態
premium_state = {}

# ✅ 口調登録管理（state更新用）
def update_user_state(user_id, next_step):
    try:
        with open("users_info.json", "r", encoding="utf-8") as f:
            users = json.load(f)
        if user_id in users:
            users[user_id]["state"] = next_step
            with open("users_info.json", "w", encoding="utf-8") as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"ユーザー状態更新失敗: {e}")

# ✅ 現在のプレミアム設定ステップを取得
def get_current_step(user_id):
    if not os.path.exists("temp_user_state.json"):
        return None
    with open("temp_user_state.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get(user_id)

# ✅ プレミアム設定用の質問リスト
premium_questions = [
    {"key": "emoji_list", "question": "【1/10】実際に使ってほしい絵文字を貼り付けてください😊"},
    {"key": "tone_tags", "question": "【2/10】使いたたい日記のテイストを教えてください（例：清楚、甘えん坊、えっち、愛され系、ドMなど）"},
    {"key": "ng_elements", "question": "【3/10】NGワード・避けたい表現を教えてください（例：下品、罵倒、汚れ、淫語など）"},
    {"key": "appeal_tags", "question": "【4/10】指名に繋がりやすいあなたの特徴を教えてください（例：恥ずかしがり屋で可愛い、ロリ系、M、妹系など）"},
    {"key": "appeal_elements", "question": "【5/10】推したい特徴や演出したい雰囲気を教えてください（例：方言、Sっぽさ、色っぽさなど）"},
    {"key": "weekly_schedule", "question": "【6/10】主に出勤する曜日や時間帯を教えてください（例：平日昼、金土メイン、夜型など）"},
    {"key": "fav_words", "question": "【7/10】よく使う言い回し・口癖を教えてください（例：ぉ兄様へ、○○だよ〜、ぴえん、えちえち、〜だよぉなど）"},
    {"key": "other_requests", "question": "【8/10】他に反映したいリクエストがあれば教えてください（なければ「なし」でOK♪）"},
    {"key": "diary_samples", "question": "【9/10】あなたが実際に書いた写メ日記をまとめて送ってください！\n※「日記」→空行→「日記」…の形式で送ってね♪\n⚠️実際の日記に空行があると複数の日記として認識してしまう為注意してね。\n10件以上の日記をくれると日記の精度が上がっていくよ♪\nNG例\nおはようございます🌞\n\n今日は晴れていて気持ちいいお天気ですね♪\n\n本日もよろしくお願い致します♪\n\n成功例\nおはようございます🌞\n今日は晴れていて気持ちいいお天気ですね♪\n本日もよろしくお願い致します♪"},
    {"key": "store_name", "question": "【10/10】在籍している店舗名を教えてください🏢"}
]

# ✅ プレミアム設定スタート
def start_premium_setting(user_id):
    premium_state[user_id] = {
        "step": 0,
        "data": {}
    }
    return """🎉【プレミアム設定スタート】🎉

これから、あなた専用の日記をもっと魅力的に仕上げるための
「プレミアム設定」の質問を順番にお送りします😊

📌最初に入力ルールのご案内です：
・複数ある場合は読点（、）で区切って1通にまとめて送ってね
・最後の質問では、複数の写メ日記をまとめて送ってもらいます
※「日記」→空行→「日記」…の形式で送ってね！

途中で止めても、また続きから再開できるので安心してね🌸

【1/10】まず、実際に使ってほしい絵文字を貼り付けてください😊"""

# ✅ プレミアム設定の各ステップ処理
def handle_premium_step(user_id, message):
    state = premium_state.get(user_id)
    if not state:
        return "⚠️ プレミアム設定が開始されていません。"

    step = state["step"]
    if step < len(premium_questions):
        key = premium_questions[step]["key"]
        state["data"][key] = message.strip()
        state["step"] += 1
        step += 1

        if step < len(premium_questions):
            return premium_questions[step]["question"]
        else:
            # ✅ 最終保存処理
            save_diary_samples(user_id, state["data"].get("diary_samples", ""))
            save_premium_settings(user_id, state["data"])
            save_premium_user_info_to_sheet(user_id, state["data"])  # ✅ ここでスプレッドに保存

            user_info = get_user_info_from_sheet(user_id)
            nickname = user_info.get("name", "未設定")
            store = state["data"].get("store_name", "未設定")
            complete_premium_registration(user_id, nickname, store)

            del premium_state[user_id]
            return "✅ プレミアム申請が完了しました！\n承認後に通知するのでお待ちください✨\n承認完了までは引き続き無料版の日記が生成できます☺"

    return "⚠️ 不明なステップです。再度設定してください。"

# ✅ プレミアム設定保存
def save_premium_settings(user_id, settings):
    if os.path.exists(PREMIUM_FILE):
        with open(PREMIUM_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {}

    data[user_id] = settings
    with open(PREMIUM_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ✅ プレミアム設定読込（キャッシュ対応）
def load_premium_settings(user_id):
    if user_id in premium_settings_cache:
        return premium_settings_cache[user_id]

    if os.path.exists(PREMIUM_FILE):
        with open(PREMIUM_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            setting = data.get(user_id, {})
            premium_settings_cache[user_id] = setting
            return setting
    return {}

# ✅ プレミアム設定中かどうかチェック
def is_in_premium_setting(user_id):
    return user_id in premium_state

# ✅ 日記サンプル保存（シート振り分け）
def save_diary_samples(user_id, diary_samples):
    keywords = {
        "shukkin": ["出勤", "おはよう", "こんにちは", "今日も出勤"],
        "taikin": ["退勤", "お疲れ様", "おやすみ", "また明日"],
        "orei": ["ありがとう", "感謝", "お礼", "嬉しい", "また会いたい"]
    }

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for diary in diary_samples.split("\n\n"):
        diary_type = "diary"
        for type_key, kw_list in keywords.items():
            if any(kw in diary for kw in kw_list):
                diary_type = type_key
                break
        append_diary_sample_to_sheet(user_id, diary_type, diary.strip(), now)