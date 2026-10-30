import json
import os
import re
import time
import feedparser
import requests

# Sozlamalar (GitHub Secrets orqali xavfsiz olinadi)
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("CHANNEL_ID", "").strip() or "@kosibiy"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

HISTORY_FILE = "sent_posts.json"
MAX_HOURS_OLD = 36  # Faqat oxirgi 36 soat ichidagi yangiliklar

# Dunyodagi eng yetakchi IT va texnologiya manbalari (RSS)
RSS_FEEDS = [
    "https://techcrunch.com/feed/",
    "https://www.theverge.com/rss/index.xml",
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://hnrss.org/frontpage",
    "https://www.bleepingcomputer.com/feed/",
]

# IT va texnologiya mavzusini aniqlash uchun kalit so'zlar
TECH_KEYWORDS = [
    "ai", "artificial intelligence", "python", "software", "cybersecurity",
    "cloud", "google", "apple", "microsoft", "openai", "developer", "startup",
    "hardware", "algorithm", "open source", "linux", "programming", "data",
    "chip", "nvidia", "robot", "api", "web", "app", "security", "tech", "model", "llm"
]

# Gemini modellarining ustuvor ro'yxati (birinchi bo'lib Gemini 3.8 va 3.5 Flash)
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


def collect_candidates(sent_posts, max_per_feed=4):
    """Barcha manbalardan oxirgi soatlardagi eng yangi IT xabarlarini to'plash."""
    candidates = []
    seen_ids = set(sent_posts)

    for feed_url in RSS_FEEDS:
        print(f"Manba tekshirilmoqda: {feed_url}")
        try:
            feed = feedparser.parse(feed_url)
            count = 0
            for entry in feed.entries:
                post_id = entry.get("id", entry.get("link"))
                link = entry.get("link", "")
                title = entry.get("title", "").strip()

                if not post_id or post_id in seen_ids or not link or not title:
                    continue

                if not is_fresh(entry):
                    continue

                if is_tech_related(entry):
                    summary = entry.get("summary", "").split("<")[0].strip()[:500]
                    candidates.append({
                        "id": post_id,
                        "title": title,
                        "summary": summary,
                        "link": link
                    })
                    seen_ids.add(post_id)
                    count += 1
                    if count >= max_per_feed:
                        break
        except Exception as e:
            print(f"Feed o'qishda xatolik ({feed_url}): {e}")

    return candidates


def select_and_format_best_news(candidates):
    """
    To'plangan xabarlar orasidan eng samarali, muhim va ommabop BITTA
    yangilikni Gemini AI orqali saralab, o'zbek tilidagi tayyor post holatiga keltirish.
    """
    if not candidates:
        return None, None

    if not GEMINI_API_KEY:
        top = candidates[0]
        text = (
            f"⚡️ <b>{top['title']}</b>\n\n"
            f"{top['summary'][:300]}...\n\n"
            f"#texnologiya #IT\n\n"
            f"🔗 <a href='{top['link']}'>Manba</a>"
        )
        return top, text

    candidates_text = ""
    for idx, c in enumerate(candidates[:10], start=1):
        candidates_text += f"[{idx}] Sarlavha: {c['title']}\nQisqacha: {c['summary']}\n\n"

    prompt = f"""Sen professional IT va texnologiyalar kanali bosh muharririsan.
Quyida bugungi eng so'nggi texnologiya yangiliklari ro'yxati keltirilgan:

{candidates_text}

Vazifang:
1. Ushbu ro'yxatdan keng ommaga eng qiziqarli, eng muhim, shov-shuvli va dolzarb bo'lgan BITTA eng yaxshi yangilikni tanla.
2. Tanlangan yangilikni o'zbek tilida Telegram kanal uchun diqqatni tortuvchi, lo'nda va ravon post ko'rinishida yozib ber.

Javobingni QAT'IY quyidagi formatda ber:
INDEX: [Tanlagan yangiliging raqami, masalan: 1]
POST:
[Mos smaylik va <b>qalin harflar bilan</b> diqqat tortuvchi sarlavha]

[2-3 ta tushunarli gapdan iborat asosiy mazmun]

[2-3 ta mos xeshteg, masalan: #IT #AI #texnologiya]"""

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
                if ai_text:
                    match = re.search(r"INDEX:\s*(\d+)", ai_text, re.IGNORECASE)
                    chosen_idx = 0
                    if match:
                        num = int(match.group(1)) - 1
                        if 0 <= num < len(candidates[:10]):
                            chosen_idx = num

                    chosen = candidates[chosen_idx]

                    if "POST:" in ai_text:
                        post_content = ai_text.split("POST:", 1)[1].strip()
                    elif match:
                        post_content = ai_text[match.end():].strip()
                    else:
                        post_content = ai_text.strip()

                    final_post = f"{post_content}\n\n🔗 <a href='{chosen['link']}'>Manba</a>"
                    print(f"Gemini ({model}) orqali {chosen_idx+1}-raqamli ommabop yangilik tanlandi: {chosen['title'][:50]}")
                    return chosen, final_post
            else:
                print(f"AI ({model}) javob kodi: {response.status_code} - {response.text[:200]}")
        except Exception as e:
            print(f"AI ({model}) xatolik: {e}")

    # AI ishlamay qolgandagi zaxira
    top = candidates[0]
    fallback = (
        f"⚡️ <b>{top['title']}</b>\n\n"
        f"{top['summary'][:300]}...\n\n"
        f"#texnologiya #IT\n\n"
        f"🔗 <a href='{top['link']}'>Manba</a>"
    )
    return top, fallback


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

    candidates = collect_candidates(sent_posts)
    print(f"Jami yangi nomzodlar soni: {len(candidates)}")

    if not candidates:
        print("Hech qanday yangi xabar topilmadi.")
        return

    chosen_entry, post_text = select_and_format_best_news(candidates)

    if chosen_entry and post_text:
        if send_to_telegram(post_text):
            sent_posts.append(chosen_entry["id"])
            save_sent_posts(sent_posts)
            print(f"Tanlangan yangilik kanalga joylandi: {chosen_entry['title']}")
        else:
            print("Telegramga yuborishda xatolik yuz berdi.")


if __name__ == "__main__":
    main()
