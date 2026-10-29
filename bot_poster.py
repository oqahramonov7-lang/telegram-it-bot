import json
import os
import re
import time
import feedparser
import requests

# Sozlamalar (GitHub Secrets orqali xavfsiz olinadi)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = os.getenv("CHANNEL_ID", "@kosibiy")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Google retires model aliases without warning, so keep this overridable
# from the environment instead of hardcoding it in the request URL.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

HISTORY_FILE = "sent_posts.json"
MAX_POSTS_PER_RUN = 3  # Bir marta ishlaganda kanalga nechta xabar yuborilsin

# Dunyodagi eng mashhur IT va texnologiya yangiliklar manbalari (RSS)
RSS_FEEDS = [
    "https://techcrunch.com/feed/",
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


class AIUnavailable(Exception):
    """Gemini produced no post; the item stays unsent so a later run retries it."""


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


def clean_html(text):
    """Make AI output safe for Telegram parse_mode=HTML.

    The model answers in Markdown often enough to matter, and Telegram rejects
    a whole message over one unbalanced tag, so convert what converts cleanly
    and strip every tag if the result still does not balance.
    """
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.S)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text, flags=re.S)

    for tag in ("b", "i", "u", "s", "code", "pre"):
        if text.count(f"<{tag}>") != text.count(f"</{tag}>"):
            return re.sub(r"<[^>]+>", "", text)
    return text


def summarize_and_translate_with_ai(title, summary, link):
    """
    Gemini AI yordamida yangilikni tahlil qilish:
    1. Haqiqatan IT/texnologiyaga oid muhim yangilik ekanini tekshiradi.
    2. O'zbek tiliga ravon, qisqa va qiziqarli Telegram post ko'rinishida tarjima qiladi.
    """
    if not GEMINI_API_KEY:
        return (
            f"⚡️ <b>{title}</b>\n\n"
            f"{summary[:300]}...\n\n"
            f"#texnologiya #IT\n\n"
            f"🔗 <a href='{link}'>Manba</a>"
        )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )

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
        "contents": [{"parts": [{"text": prompt}]}],
        # Thinking tokens come out of the same budget as the answer, and the
        # default budget cut posts off mid-sentence, leaving an unclosed <b>
        # tag that Telegram refuses to render.
        "generationConfig": {
            "maxOutputTokens": 2048,
            "thinkingConfig": {"thinkingLevel": "low"},
        },
    }

    # 429 and 5xx mean Google is busy, not that the request is wrong, so those
    # are worth another attempt; anything else fails immediately.
    retryable = {429, 500, 502, 503, 504}
    backoff = (2, 6)
    last_error = "noma'lum xatolik"

    for attempt in range(len(backoff) + 1):
        try:
            response = requests.post(
                url,
                json=payload,
                headers={"x-goog-api-key": GEMINI_API_KEY},
                timeout=60,
            )
        except requests.RequestException as exc:
            last_error = f"so'rov uzildi: {exc}"
        else:
            if response.status_code == 200:
                data = response.json()
                candidate = (data.get("candidates") or [{}])[0]
                finish_reason = candidate.get("finishReason")
                ai_text = "".join(
                    part.get("text", "")
                    for part in candidate.get("content", {}).get("parts", [])
                ).strip()

                if finish_reason not in (None, "STOP"):
                    # A half-written post is not worth sending.
                    last_error = f"javob tugallanmadi (finishReason={finish_reason})"
                    break
                if not ai_text or ai_text.upper() == "SKIP":
                    return None  # AI bu yangilikni IT emas deb hisobladi
                post = clean_html(ai_text)
                return f"{post}\n\n🔗 <a href='{link}'>Manba</a>"

            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            if response.status_code not in retryable:
                break

        if attempt < len(backoff):
            print(f"AI urinish {attempt + 1} muvaffaqiyatsiz ({last_error}), qayta urinamiz")
            time.sleep(backoff[attempt])

    raise AIUnavailable(last_error)


def send_to_telegram(post_text):
    """Tayyor xabarni Telegram kanalga jo'natish."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": post_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    response = requests.post(url, json=payload, timeout=20)
    if response.status_code == 200:
        print("Xabar muvaffaqiyatli yuborildi!")
        return True
    else:
        print(f"Telegram xatolik: {response.text}")
        return False


def main():
    sent_posts = load_sent_posts()
    newly_sent = 0

    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries[:5]:
            post_id = entry.get("id", entry.get("link"))
            link = entry.get("link", "")

            if not post_id or post_id in sent_posts:
                continue

            if is_tech_related(entry):
                clean_summary = entry.get("summary", "").split("<")[0].strip()[:600]
                try:
                    uzbek_post = summarize_and_translate_with_ai(
                        entry.get("title", ""), clean_summary, link
                    )
                except AIUnavailable as exc:
                    # Posting the untranslated source text is worse than posting
                    # nothing, so leave the item unsent for the next run.
                    print(f"AI tarjima qilib bermadi, yurish to'xtatiladi: {exc}")
                    save_sent_posts(sent_posts)
                    return

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


if __name__ == "__main__":
    main()
