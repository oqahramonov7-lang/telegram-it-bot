import json
import os
import time
import feedparser
import requests

# Sozlamalar (GitHub Secrets orqali xavfsiz olinadi)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip() or "@kosibiy"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

HISTORY_FILE = "sent_posts.json"
MAX_POSTS_PER_RUN = 3  # Bir marta ishlaganda kanalga nechta xabar yuborilsin

# Dunyodagi eng mashhur IT va texnologiya yangiliklar manbalari (RSS)
RSS_FEEDS = [
    "https://feeds.feedburner.com/TechCrunch/",
    "https://www.theverge.com/rss/index.xml",
    "https://hnrss.org/frontpage",
    "https://habr.com/ru/rss/hubs/it/all/",
]

# Boshlang'ich filtrlash uchun kalit so'zlar
TECH_KEYWORDS = [
    "ai", "artificial intelligence", "python", "software", "cybersecurity",
    "cloud", "google", "apple", "microsoft", "openai", "developer", "startup",
    "hardware", "algorithm", "open source", "linux", "programming", "data",
    "chip", "nvidia", "robot", "api", "web", "app", "security", "tech"
]


def load_sent_posts():
    """Avval yuborilgan xabarlar ro'yxatini yuklash (takrorlanmasligi uchun)."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_sent_posts(posts):
    """Oxirgi 200 ta yuborilgan xabar ID raqamini saqlab qo'yish."""
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(posts[-200:], f, ensure_ascii=False, indent=2)


def is_tech_related(entry):
    """Xabar IT va texnologiyaga aloqadorligini tekshirish."""
    text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
    return any(keyword in text for keyword in TECH_KEYWORDS)


def get_available_gemini_models():
    """Gemini API da ushbu kalit uchun mavjud modellarni aniqlash."""
    if not GEMINI_API_KEY:
        return []
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            models = [
                m.get("name", "").replace("models/", "")
                for m in data.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
            print(f"Mavjud Gemini modellari: {models}")
            return models
        else:
            print(f"Gemini ModelService xatolik: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Gemini ModelService ulanish xatoligi: {e}")
    return []


def summarize_and_translate_with_ai(title, summary, link, available_models):
    """
    Gemini AI yordamida yangilikni tahlil qilish:
    1. Haqiqatan IT/texnologiyaga oid muhim yangilik ekanini tekshiradi.
    2. O'zbek tiliga ravon, qisqa va qiziqarli Telegram post ko'rinishida tarjima qiladi.
    """
    fallback_post = (
        f"⚡️ <b>{title}</b>\n\n"
        f"{summary[:300]}...\n\n"
        f"#texnologiya #IT\n\n"
        f"🔗 <a href='{link}'>Manba</a>"
    )

    if not GEMINI_API_KEY:
        return fallback_post

    prompt = f"""Sen IT va texnologiyalar bo'yicha Telegram kanal muharririsan.
Quyidagi yangilikni ko'rib chiq:

Sarlavha: {title}
Qisqacha matn: {summary}

Vazifang:
1. Agar bu yangilik IT, dasturlash, sun'iy intellekt, gadjetlar yoki texnologiyaga UMUMAN aloqasi bo'lmasa (masalan, kino, siyosat yoki oddiy reklama bo'lsa), faqatgina "SKIP" deb javob qaytar.
2. Agar IT va texnologiyaga oid bo'lsa, uni o'zbek tilida Telegram kanal uchun chiroyli post ko'rinishida yozib ber.
Format talablari:
- Birinchi qatorda mos smaylik va qalin harflar bilan qiziqarli sarlavha (HTML <b> tegida, masalan: ⚡️ <b>Sarlavha shu yerda</b>).
- Keyin 2-3 gapdan iborat asosiy mazmuni (oddiy va tushunarli tilda).
- Oxirida mavzuga mos 2-3 ta xeshteg (#texnologiya #IT #AI kabi).
- Hech qanday qo'shimcha izoh yozma, faqat tayyor post matnini qaytar."""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    # Sinab ko'rish uchun modellar ro'yxati
    candidate_models = list(available_models)
    for default_m in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-latest"]:
        if default_m not in candidate_models:
            candidate_models.append(default_m)

    for model in candidate_models:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={GEMINI_API_KEY}"
        )
        try:
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                ai_text = (
                    data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
                    .strip()
                )
                if ai_text and ai_text.upper() != "SKIP":
                    return f"{ai_text}\n\n🔗 <a href='{link}'>Manba</a>"
                elif ai_text.upper() == "SKIP":
                    return None
            else:
                print(f"AI ({model}) javob kodi: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"AI ({model}) xatolik: {e}")

    return fallback_post


def send_to_telegram(post_text):
    """Tayyor xabarni Telegram kanalga jo'natish."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": post_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 200:
            print(f"Xabar muvaffaqiyatli yuborildi ({CHANNEL_ID})!")
            return True
        else:
            print(f"Telegram xatolik: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Telegram ulanish xatoligi: {e}")
        return False


def main():
    print(f"Bot ishga tushdi. Kanal: {CHANNEL_ID}")
    sent_posts = load_sent_posts()
    newly_sent = 0

    available_models = get_available_gemini_models()

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:5]:
            post_id = entry.get("id", entry.get("link"))
            link = entry.get("link", "")

            if not post_id or post_id in sent_posts:
                continue

            if is_tech_related(entry):
                clean_summary = entry.get("summary", "").split("<")[0].strip()[:600]
                uzbek_post = summarize_and_translate_with_ai(
                    entry.get("title", ""), clean_summary, link, available_models
                )

                if uzbek_post:
                    if send_to_telegram(uzbek_post):
                        sent_posts.append(post_id)
                        newly_sent += 1
                        time.sleep(3)

                    if newly_sent >= MAX_POSTS_PER_RUN:
                        break
                else:
                    sent_posts.append(post_id)

        if newly_sent >= MAX_POSTS_PER_RUN:
            break

    save_sent_posts(sent_posts)
    print(f"Tugatildi. Yangi yuborilgan postlar soni: {newly_sent}")


if __name__ == "__main__":
    main()
