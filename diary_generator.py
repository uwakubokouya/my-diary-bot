import random
from openai import OpenAI
import os

from premium_setting import load_premium_settings
from premium_utils import get_user_diary_samples, increment_diary_usage
from tone_utils import adjust_tone_style, get_topic_by_tone
from google_sheets import get_positive_feedback, connect_sheet, increment_template_usage

# ✅ OpenAI クライアントの初期化（v1以降必須）
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY").strip())

# ✅ テンプレートキャッシュ
template_cache = {}

# ✅ 日記タイプとタブ名の対応
TAB_MAPPING = {
    "shukkin": "ShukkinTemplates",
    "taikin": "TaikinTemplates",
    "orei": "OreiTemplates"
}

# ✅ 日記タイプ別の目的文
DIARY_PURPOSES = {
    "shukkin": "この日記は『出勤していることを伝え、当日の空き枠や得意なサービス、自分の魅力を自然に伝えて来店につなげる』ためのものです。",
    "taikin": "この日記は『本日の勤務終了を伝え、感謝・満了アピール・次回の出勤予定・軽いプライベート要素を含めてファン化を促す』ためのものです。",
    "orei": "この日記は『今日来てくれた特定のお客様への感謝を綴りつつ、その思い出や雰囲気を通して新規のお客様に自分の魅力を伝える』ためのものです。"
}

# ✅ 無料ユーザー用プロンプト
FREE_PROMPTS = {
    "shukkin": (
        "あなたは人気風俗キャストです。本日出勤していることを自然な流れで伝えつつ、"
        "空き枠案内・得意サービス・明るい雰囲気を織り交ぜ、親近感ある文章で日記を作成してください。\n\n"
    ),
    "taikin": "あなたは人気風俗キャストです。本日の退勤を優しく自然に伝え、感謝、満了アピール、次回予定、プライベート感をバランスよく盛り込んだ日記を作成してください。",
    "orei": (
        "あなたは人気風俗キャストです。今日来てくれた“特定のお客様”に向けた自然なお礼日記を作成してください。\n\n"
        "・呼びかけは「○○さん」や「○○さま」など個人向けにしてください。\n"
        "・お客様と交わした会話、反応、印象に残った出来事をできるだけ具体的に書いてください。\n"
        "・気持ちよさそうなリアクションや甘えた姿にキュンとしたなど、あなた自身の感情も自然に込めてください。\n"
        "・ぬるぬる、くっつき、マッサージなどの体験に関する描写を含めてもOKです。\n"
        "・自然で柔らかい文体、絵文字も適度に使って構いません。\n"
        "・文章の冒頭は『今日は〜』ではなく、その方とのやりとりにすっと入れるようにしてください。\n"
    )
}

def get_templates_with_cache(tab_name):
    if tab_name not in template_cache:
        sheet = connect_sheet("DiaryTemplates", tab_name)
        records = sheet.get_all_records()
        templates = {}
        for row in records:
            section = row.get("section", "").strip()
            text = row.get("text", "").strip()
            if section and text:
                if section not in templates:
                    templates[section] = []
                templates[section].append(text)
        template_cache[tab_name] = templates
    return template_cache[tab_name]

def sanitize_diary_text(text, username):
    return text.replace(f"{username}さん", "お客様").replace(f"{username}様", "お客様")

def generate_free_diary(user_info, diary_type, reference_examples=""):
    prompt = f"""
{FREE_PROMPTS.get(diary_type, "あなたは風俗キャストです。自然な写メ日記を書いてください。")}

🎀 キャラ情報
・源氏名：{user_info['name']}
・年代：{user_info['age_range']}
・口調：{user_info['tone']}

✏️ 参考例：
{reference_examples}

📝 1通だけ自然な日記を書いてください。
日記の出だしは毎回違う自然な入り方にしてください。「今日も〇〇です」のような出だしは避けてください。
"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo-0125",
        messages=[
            {"role": "system", "content": "あなたは自然な雰囲気で日記を書く風俗キャストです。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.85
    )
    return response.choices[0].message.content.strip()

def generate_premium_diary(user_info, diary_type, diary_samples, premium, keyword_text=None):
    diary_goal = DIARY_PURPOSES.get(diary_type, "自然な写メ日記を書く")
    premium_text = f"""
【プレミアム設定】
使用絵文字: {premium.get("emoji_list", "")}
日記テイスト: {premium.get("tone_tags", "")}
避けたい表現: {premium.get("ng_elements", "")}
推したい特徴: {premium.get("appeal_elements", "")}
得意ポイント: {premium.get("appeal_tags", "")}
出勤傾向: {premium.get("weekly_schedule", "")}
口癖: {premium.get("fav_words", "")}
要望: {premium.get("other_requests", "")}
"""
    keyword_section = f"\n【キーワード】{keyword_text}" if keyword_text else ""

    prompt = f"""
あなたは風俗キャストで人気者です。

🎯 目的
{diary_goal}

【キャスト情報】
源氏名: {user_info['name']}
年代: {user_info['age_range']}
口調: {user_info['tone']}
{premium_text}
{keyword_section}

【参考日記】
{diary_samples}

📝 これらを踏まえた自然な1通の日記を作成してください。
"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo-0125",
        messages=[
            {"role": "system", "content": "あなたは自然な雰囲気で日記を書くプロフェッショナルな風俗キャストです。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.85
    )
    return response.choices[0].message.content.strip()

def generate_simple_diary(user_info, diary_type, keyword_text=None):
    user_id = user_info["user_id"]
    is_premium = user_info.get("is_premium", False)

    if is_premium:
        premium = load_premium_settings(user_id)
        user_diaries = get_user_diary_samples(user_id, diary_type)
        diary_samples = "\n".join(random.sample(user_diaries, min(len(user_diaries), 5))) if user_diaries else ""

        for diary in user_diaries:
            increment_diary_usage(user_id, diary)

        generated_text = generate_premium_diary(user_info, diary_type, diary_samples, premium, keyword_text)
        return adjust_tone_style(
            generated_text,
            user_info["tone"],
            user_info["name"],
            fav_words=premium.get("fav_words", ""),
            other_requests=premium.get("other_requests", "")
        )

    reference_examples = ""
    feedbacks = get_positive_feedback(user_id, diary_type)

    if diary_type == "orei" and len(feedbacks) >= 10:
        tab_name = TAB_MAPPING.get(diary_type, "")
        templates = get_templates_with_cache(tab_name)
        sheet = connect_sheet("DiaryTemplates", tab_name)
        records = sheet.get_all_records()

        selected_templates = []
        for section, texts in templates.items():
            if texts:
                selected = random.choice(texts)
                selected_templates.append(selected)
                increment_template_usage(sheet, section, selected, records)
                if len(selected_templates) >= 3:
                    break

        selected_feedbacks = random.sample(feedbacks, 2)
        combined = selected_templates + selected_feedbacks
        random.shuffle(combined)
        reference_examples = "\n".join(combined)

    else:
        if len(feedbacks) >= 10:
            reference_examples = "\n".join(feedbacks[:5])
        else:
            tab_name = TAB_MAPPING.get(diary_type, "")
            templates = get_templates_with_cache(tab_name)
            selected_texts = []
            sheet = connect_sheet("DiaryTemplates", tab_name)
            records = sheet.get_all_records()

            for section, texts in templates.items():
                if texts:
                    selected = random.choice(texts)
                    selected_texts.append(selected)
                    increment_template_usage(sheet, section, selected, records)

            reference_examples = "\n".join(selected_texts)

    generated_text = generate_free_diary(user_info, diary_type, reference_examples)
    return adjust_tone_style(generated_text, user_info["tone"], user_info["name"])
