import json
import os
import re
import time
import feedparser
import requests

# Agar .env fayli mavjud bo'lsa, sozlamalarni yuklab oladi (lokal kompyuter uchun)
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(ENV_FILE):
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().strip("'\""))
    except Exception as e:
        print(f".env faylini o'qishda xatolik: {e}")

# Sozlamalar (Lokal .env yoki GitHub Secrets orqali olinadi)
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

# Gemini modellarining ustuvor ro'yxati (tezkor va barqaror modellar)
PREFERRED_MODELS = [
    os.getenv("GEMINI_MODEL", "").strip(),
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
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


def sanitize_uzbek_text(text):
    """Matndagi begona yoki buzilgan belgilarni (masalan, arabcha harflar) tozalash."""
    if not text:
        return ""
    # O'zbek lotin matniga tasodifan tushib qoladigan arabcha harflarni tuzatish
    text = text.replace("lرزatgan", "larzatgan")
    text = text.replace("رز", "rz")
    # Arab va boshqa begona yozuvdagi belgilarni tozalash
    text = re.sub(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]", "", text)
    return text.strip()


def find_best_matching_candidate(candidates_subset, ai_text, default_idx=0):
    """
    Agar AI qaytargan ID shubhali bo'lsa yoki xato bo'lsa,
    AI matnidagi kalit so'zlarni nomzodlar sarlavhalari bilan solishtirib eng mosini topish.
    """
    clean_ai = re.sub(r"[^\w\s]", " ", ai_text.lower())
    ai_words = set(w for w in clean_ai.split() if len(w) > 3)

    best_idx = default_idx
    best_score = 0

    for idx, cand in enumerate(candidates_subset):
        cand_text = f"{cand.get('title', '')} {cand.get('summary', '')}".lower()
        cand_words = set(w for w in re.sub(r"[^\w\s]", " ", cand_text).split() if len(w) > 3)
        common = ai_words.intersection(cand_words)
        score = len(common)
        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx


def select_and_format_best_news(candidates):
    """
    To'plangan xabarlar orasidan eng samarali, muhim va ommabop BITTA
    yangilikni Gemini AI orqali saralab, o'zbek tilidagi tayyor post holatiga keltirish.
    """
    if not candidates:
        return None, None

    # Eng so'nggi 15 ta nomzodni ko'rib chiqishga taqdim etamiz
    candidates_subset = candidates[:15]

    if not GEMINI_API_KEY:
        top = candidates_subset[0]
        text = (
            f"⚡️ <b>{top['title']}</b>\n\n"
            f"{top['summary'][:300]}...\n\n"
            f"#texnologiya #IT\n\n"
            f"🔗 <a href='{top['link']}'>Manba</a>"
        )
        return top, text

    candidates_text = ""
    for idx, c in enumerate(candidates_subset, start=1):
        candidates_text += f"[ID: {idx}] Sarlavha: {c['title']}\nManba havolasi: {c['link']}\nQisqacha: {c['summary']}\n\n"

    prompt = f"""Sen professional IT va texnologiyalar kanali bosh muharririsan.
Quyida bugungi eng so'nggi texnologiya yangiliklari ro'yxati keltirilgan:

{candidates_text}

Vazifang:
1. Ushbu ro'yxatdan keng ommaga eng qiziqarli, eng muhim, shov-shuvli va dolzarb bo'lgan BITTA eng yaxshi yangilikni tanla.
2. Tanlangan yangilikni o'zbek tilida Telegram kanal uchun diqqatni tortuvchi, lo'nda va ravon post ko'rinishida tayyorla.

QAT'IY TALABLAR:
- Faqat toza O'zbek lotin alifbosidan foydalan. Arab, kirill yoki begona harflar aralashmasin (masalan 'lrzatgan' kabi xatolarga yo'l qo'yma, to'g'ri so'z: 'larzatgan'). Imlo va uslub juda ravon, xatosiz bo'lsin.
- Xabar matni tanlangan yangilik (selected_id) mazmuniga 100% mos kelishi shart.
- Javobingni FAQAT quyidagi JSON formatida ber:
{{
  "selected_id": 1,
  "headline": "Mos smaylik va diqqat tortuvchi sarlavha",
  "body": "2-3 ta tushunarli, ravon gapdan iborat asosiy mazmun",
  "hashtags": "#Kripto #Xavfsizlik #IT"
}}"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json"
        }
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
                    # JSON parse qilishga urinib ko'ramiz
                    parsed_json = None
                    try:
                        parsed_json = json.loads(ai_text)
                    except Exception:
                        json_match = re.search(r"\{.*\}", ai_text, re.DOTALL)
                        if json_match:
                            try:
                                parsed_json = json.loads(json_match.group(0))
                            except Exception:
                                pass

                    chosen_idx = 0
                    if parsed_json and isinstance(parsed_json, dict):
                        sel_id = parsed_json.get("selected_id")
                        try:
                            num = int(sel_id) - 1
                            if 0 <= num < len(candidates_subset):
                                chosen_idx = num
                            else:
                                chosen_idx = find_best_matching_candidate(candidates_subset, ai_text, 0)
                        except (ValueError, TypeError):
                            chosen_idx = find_best_matching_candidate(candidates_subset, ai_text, 0)

                        headline = sanitize_uzbek_text(parsed_json.get("headline", ""))
                        body = sanitize_uzbek_text(parsed_json.get("body", ""))
                        hashtags = sanitize_uzbek_text(parsed_json.get("hashtags", ""))

                        # Sarlavhani qalin (bold) qilish
                        if headline and not ("<b>" in headline and "</b>" in headline):
                            parts = headline.split(" ", 1)
                            if len(parts) == 2 and any(ord(char) > 127 for char in parts[0]):
                                headline = f"{parts[0]} <b>{parts[1]}</b>"
                            else:
                                headline = f"<b>{headline}</b>"

                        chosen = candidates_subset[chosen_idx]
                        final_post = f"{headline}\n\n{body}\n\n{hashtags}\n\n🔗 <a href='{chosen['link']}'>Manba</a>"
                        print(f"Gemini ({model}) orqali {chosen_idx+1}-raqamli yangilik tanlandi: {chosen['title'][:60]}")
                        return chosen, final_post

                    # JSON bo'lmagan holat uchun zaxira tahlil
                    match = re.search(r'(?:selected_id|INDEX|TANLANGAN|ID)\s*["\':=]*\s*\[?(\d+)\]?', ai_text, re.IGNORECASE)
                    if match:
                        num = int(match.group(1)) - 1
                        if 0 <= num < len(candidates_subset):
                            chosen_idx = num
                        else:
                            chosen_idx = find_best_matching_candidate(candidates_subset, ai_text, 0)
                    else:
                        chosen_idx = find_best_matching_candidate(candidates_subset, ai_text, 0)

                    chosen = candidates_subset[chosen_idx]
                    cleaned_content = sanitize_uzbek_text(ai_text)
                    final_post = f"{cleaned_content}\n\n🔗 <a href='{chosen['link']}'>Manba</a>"
                    print(f"Gemini ({model}) zaxira rejimida {chosen_idx+1}-raqamli yangilik tanlandi: {chosen['title'][:60]}")
                    return chosen, final_post
            else:
                print(f"AI ({model}) javob kodi: {response.status_code} - {response.text[:200]}")
                time.sleep(2)
        except Exception as e:
            print(f"AI ({model}) xatolik: {e}")
            time.sleep(2)

    # Agar barcha AI modellari xatolik bersa yoki band bo'lsa:
    # QAT'IY QOIDA: Kanalga inglizcha xom xabar yuborilmaydi!
    print("❌ Barcha AI modellari xatolik berdi yoki vaqtincha band. Xabar o'zbek tiliga tarjima qilinmagani sababli kanalga yuborilmaydi.")
    return None, None


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
