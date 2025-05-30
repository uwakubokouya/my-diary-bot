import os
import json
import openai
import threading
import datetime
import traceback
import hmac
import hashlib
import base64
import time
import logging
import sys

from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent

from tone_utils import get_welcome_message
from google_sheets import (
    is_test_user, append_user_to_sheet, append_user_diary_entry,
    get_usage_count, log_usage, get_approved_users, log_feedback,
    get_newly_approved_users, mark_premium_notified, append_diary_sample_to_sheet,
    connect_sheet, get_user_info
)
from premium_setting import (
    start_premium_setting, is_in_premium_setting, handle_premium_step,
    load_premium_settings, save_diary_samples, get_current_step, update_user_state,
    premium_state
)
from user_register import handle_registration_step, is_registering
from diary_generator import generate_simple_diary

# ログ設定
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# ログフォーマット
log_format = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# ファイルログ設定（app.log）
file_handler = logging.FileHandler("app.log", encoding="utf-8")
file_handler.setFormatter(log_format)

# 標準出力ログ設定（Renderのログタブにも出る）
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_format)

# ルートロガー設定
logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])

# 外部モジュールのログレベル調整
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

# 環境変数読み込み
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path, override=True)

openai.api_key = os.getenv("OPENAI_API_KEY").strip()
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN").strip())
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET").strip())

app = Flask(__name__)

# 各種ステート
latest_diaries = {}
pending_keyword_request = {}
temporary_keywords = {}
adding_diary_users = set()
user_status = {}

os.makedirs("diary_data/sample", exist_ok=True)
os.makedirs("feedback/good", exist_ok=True)
os.makedirs("feedback/bad", exist_ok=True)

DIARY_TYPE_MAP = {
    "1": "shukkin",
    "2": "taikin",
    "3": "orei"
}

def get_diary_type(text):
    if "出勤" in text:
        return "shukkin"
    elif "退勤" in text:
        return "taikin"
    elif "お礼" in text:
        return "orei"
    else:
        return None

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    channel_secret = os.getenv("LINE_CHANNEL_SECRET").strip().encode('utf-8')
    body_bytes = body.encode('utf-8')
    hash = hmac.new(channel_secret, body_bytes, hashlib.sha256).digest()
    expected_signature = base64.b64encode(hash).decode('utf-8')

    if not hmac.compare_digest(signature, expected_signature):
        print("❌ 検証NG！署名が一致しません")
        abort(400)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ LINE SDKレベルの署名検証に失敗")
        abort(400)
    return "OK"

@app.route("/", methods=["GET", "HEAD"])
def health_check():
    return "OK", 200

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    logging.info(f"[フォロー] user_id={user_id}")
    welcome_text = get_welcome_message()
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=welcome_text))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        user_id = event.source.user_id
        message_text = event.message.text.strip()

        # 登録の競合を防ぐためのチェック
        if is_registering(user_id) and message_text == "プレミアム登録":
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 情報登録が進行中です。完了後にプレミアム登録を行ってください。"))
            return

        if is_in_premium_setting(user_id) and message_text == "情報を登録する":
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ プレミアム登録が進行中です。完了後に情報登録を行ってください。"))
            return

        logging.info(f"[受信] user_id={user_id}, message='{message_text}'")

        if user_id in premium_state and message_text == "情報を登録する":
            del premium_state[user_id]
        if user_id in user_status and message_text == "情報を登録する":
            del user_status[user_id]

        if message_text == "プレミアム登録":
            user_info = get_user_info(user_id)
            if user_info and user_info.get("is_premium") == True:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="✅ 現在プレミアム登録済みです。\n変更をご希望の場合は「変更希望」と送ってね😊")
                )
                return
            reply = start_premium_setting(user_id)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return

        if message_text == "情報を登録する":
            logging.info(f"[登録開始] user_id={user_id}")
            reply = handle_registration_step(user_id, None)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return

        if is_registering(user_id):
            reply = handle_registration_step(user_id, message_text)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return

        if is_in_premium_setting(user_id):
            reply = handle_premium_step(user_id, message_text)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return

        if message_text == "日記追加":
            if user_id in get_approved_users():
                user_status[user_id] = {"mode": "select_diary_type"}
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage("追加する日記の種類を番号で教えてね\n1.出勤\n2.退勤\n3.お礼")
                )
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage("⚠️ この機能はプレミアムユーザー限定です。"))
            return
        if user_status.get(user_id, {}).get("mode") == "select_diary_type":
            diary_type = DIARY_TYPE_MAP.get(message_text)
            if diary_type:
                user_status[user_id] = {"mode": "diary_add", "diary_type": diary_type}
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"✏️ {diary_type}追加モードになりました。\n空行で区切って複数の日記を送ってね♪")
                )
            else:
                line_bot_api.reply_message(event.reply_token, TextSendMessage("番号は 1〜3 の中から選んでね♪"))
            return

        if user_status.get(user_id, {}).get("mode") == "diary_add":
            diary_type = user_status[user_id]["diary_type"]
            entries = [e.strip() for e in message_text.split("\n\n") if e.strip()]
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet = connect_sheet("DiaryUserData", "PremiumDiarySamples")
            for entry in entries:
                sheet.append_row([user_id, diary_type, now, entry])
            user_status[user_id] = {}
            line_bot_api.reply_message(event.reply_token, TextSendMessage(f"✅ {len(entries)}件の日記を追加しました！ありがとう♪"))
            return

        if message_text in ["👍", "👎"] and user_id in latest_diaries:
            feedback_type = "good" if message_text == "👍" else "bad"
            folder = os.path.join("feedback", feedback_type, user_id)
            os.makedirs(folder, exist_ok=True)
            diary_data = latest_diaries[user_id]
            filename = f"{diary_data['type']}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(os.path.join(folder, filename), "w", encoding="utf-8") as f:
                f.write(diary_data['text'])
            log_feedback(user_id=user_id, diary_type=diary_data['type'], result=feedback_type, diary_text=diary_data['text'])
            line_bot_api.reply_message(event.reply_token, TextSendMessage("フィードバックありがとうございます！保存しました✨"))
            return

        approved_users = get_approved_users()
        user_info = get_user_info(user_id)
        if not user_info or not user_info.get("name") or not user_info.get("tone"):
             line_bot_api.reply_message(
                 event.reply_token,
                 TextSendMessage(
                     text="📝 まだ情報登録が完了していないみたいです。\n「情報を登録する」と送って、先にユーザー登録をしてくださいね♪"
                 )
             )
             return

        if not user_info:
            line_bot_api.reply_message(event.reply_token, TextSendMessage("ユーザー情報が見つかりません。『情報を登録する』と送ってね♪"))
            return

        if user_id in pending_keyword_request:
            diary_type = pending_keyword_request.pop(user_id)
            keyword_text = message_text if user_id in approved_users else None
            if keyword_text:
                temporary_keywords[user_id] = keyword_text
            log_usage(user_id)
            generated_diary = generate_simple_diary(user_info, diary_type, keyword_text)
            latest_diaries[user_id] = {"type": diary_type, "text": generated_diary}
            reply_text = f"📝 生成された日記：\n{generated_diary}\n\n気に入ったら「👍」微妙なら「👎」で教えてね♪"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            return

        diary_type = get_diary_type(message_text)

        if diary_type and user_id in approved_users:
            pending_keyword_request[user_id] = diary_type
            line_bot_api.reply_message(
               event.reply_token,
                TextSendMessage("📝 入れて欲しいキーワードや内容があれば、読点（、）で区切って教えてください♪")
            )
            return


        usage_count = get_usage_count(user_id)
        if usage_count >= 3 and not is_test_user(user_id):
            reply_text = (
                "⚠️ 本日の無料分はこれでラストだよっ💦\n"
                "明日また会えるの楽しみにしてるねっ💕\n"
                "▶️ プレミアム登録すれば制限なしで使えるよ！"
            )
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
            return

        log_usage(user_id)
        generated_diary = generate_simple_diary(user_info, diary_type)
        latest_diaries[user_id] = {"type": diary_type, "text": generated_diary}
        reply_text = f"📝 生成された日記：\n{generated_diary}\n\n気に入ったら「👍」微妙なら「👎」で教えてね♪"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

    except Exception:
        traceback.print_exc()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 内部エラーが発生しました。"))

def notify_newly_approved_users():
    while True:
        try:
            newly_approved = get_newly_approved_users()
            for row in newly_approved:
                user_id = row.get("user_id")
                if user_id:
                    message = (
                        "✅ プレミアム登録が承認されました！\n"
                        "いつでもプレミアム設定が反映された写メ日記を作れるよ✨\n"
                        "「出勤」「退勤」「お礼」って送ってね😊"
                    )
                    line_bot_api.push_message(user_id, TextSendMessage(text=message))
                    mark_premium_notified(user_id)
        except Exception as e:
            print("❌ プレミアム承認チェック中にエラー:", e)
        time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=notify_newly_approved_users, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
