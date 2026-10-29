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
MAX_HOURS_OLD = 36     # 36 soatdan eski xabarlarni tashlab yuborish (faqat yangi xabarlar)

# Dunyodagi eng mashhur va yangi IT xabarlar manbalari (haqiqiy RSS)
RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://hnrss.org/frontpage",
    "https://www.bleepingcomputer.com/feed/",
]

# Boshlang'ich filtrlash uchun kalit so'zlar
TECH_KEYWORDS = [
    "ai", "artificial intelligence", "python", "software", "cybersecurity",
    "cloud", "google", "apple", "microsoft", "openai", "developer", "startup",
    "hardware", "algorithm", "open source", "linux", "programming", "data",
    "chip", "nvidia", "robot", "api", "web", "app", "security", "tech", "model", "llm"
]

# Gemini modellarining ustuvor ro'yxati (birinchi bo'lib Gemini 3.8 Flash)
PREFERRED_MODELS = [
    os.getenv("GEMINI_MODEL", "").strip(),
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-3.1-pro-preview"
]
PREFERRED_MODELS = [m for m in PREFERRED_MODELS if m]


def load_sent_posts():
    """Avval yuborilgan xabarlar ro'yxatini yuklash."""
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


def is_fresh(entry, max_hours=MAX_HOURS_OLD):
    """Xabar eskirib qolmaganligini tekshirish (oxirgi max_hours soat)."""
    pub_time = entry.get("published_parsed") or entry.get("updated_parsed")
    if pub_time:
        try:
            pub_timestamp = time.mktime(pub_time)
            age_hours = (time.time() - pub_timestamp) / 3600
            if age_hours > max_hours:
                return False
        except Exception:
            pass
    return True


def summarize_and_translate_with_ai(title, summary, link):
    """
    Gemini AI yordamida eng yangi xabarni tahlil qilish va o'zbek tiliga
    Telegram kanal uchun chiroyli post ko'rinishida tayyorlash.
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
Quyidagi eng so'nggi yangilikni ko'rib chiq:

Sarlavha: {title}
Qisqacha matn: {summary}

Vazifang:
1. Agar bu yangilik IT, dasturlash, sun'iy intellekt, gadjetlar yoki texnologiyaga UMUMAN aloqasi bo'lmasa, faqatgina "SKIP" deb javob qaytar.
2. Agar IT va texnologiyaga oid bo'lsa, uni o'zbek tilida Telegram kanal uchun qiziqarli, o'qishli va lo'nda post qilib yozib ber.
Format talablari:
- Birinchi qatorda mavzuga mos smaylik va qalin harflar bilan diqqat tortuvchi sarlavha (HTML <b> tegida, masalan: ⚡️ <b>...</b>).
- Keyin 2-3 ta tushunarli gapda yangilikning eng muhim mazmuni.
- Oxirida 2-3 ta mos xeshteg (#AI #texnologiya #IT kabi).
- Hech qanday boshqa izoh yoki muqaddima yozma, faqat tayyor post matnini qaytar."""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    for model in PREFERRED_MODELS:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={GEMINI_API_KEY}"
        )
        try:
            response = requests.post(url, json=payload, timeout=25)
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
                    print(f"Post Gemini ({model}) orqali tarjima qilindi.")
                    return f"{ai_text}\n\n🔗 <a href='{link}'>Manba</a>"
                elif ai_text.upper() == "SKIP":
                    print(f"Yangilik mavzuga to'g'ri kelmadi (SKIP): {title[:40]}...")
                    return None
            else:
                print(f"AI ({model}) javob kodi: {response.status_code} - {response.text[:200]}")
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

    for feed_url in RSS_FEEDS:
        print(f"Manba tekshirilmoqda: {feed_url}")
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:8]:
            post_id = entry.get("id", entry.get("link"))
            link = entry.get("link", "")
            title = entry.get("title", "")

            if not post_id or post_id in sent_posts:
                continue

            # Faqat oxirgi 36 soat ichida chiqqan yangi xabarlarni olamiz
            if not is_fresh(entry):
                continue

            if is_tech_related(entry):
                print(f"Yangi xabar topildi: {title[:60]}")
                clean_summary = entry.get("summary", "").split("<")[0].strip()[:600]
                uzbek_post = summarize_and_translate_with_ai(
                    title, clean_summary, link
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
