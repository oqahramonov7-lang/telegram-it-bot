# 🤖 Telegram IT News Bot

Dunyoning yetakchi IT manbalaridan (TechCrunch, The Verge, Hacker News, Habr) eng so'nggi texnologiya yangiliklarini RSS orqali olib, **Gemini AI** yordamida o'zbek tiliga qiziqarli va qisqa Telegram post formatida tarjima qiluvchi va Telegram kanalga avtomatik yuklovchi bot.

---

## 🚀 Imkoniyatlari

- 📡 **RSS agregatsiya**: TechCrunch, The Verge, Hacker News va Habr'dan eng yangi postlarni tekshirish.
- 🎯 **Kalit so'zlar bo'yicha filtrlash**: Faqat IT, AI, dasturlash va texnologiyaga tegishli postlarni saralash.
- 🧠 **Gemini AI saralash va tahlil**: Yangiliklar orasidan eng muhim, ommabop va qiziqarlisini tanlab, o'zbek tilida tayyor Telegram post (sarlavha, qisqa sharh va xeshteglar) tayyorlash.
- ⏰ **Avtomatik jadval (GitHub Actions)**: Kuniga 3 marta (`09:00`, `13:00`, `19:00` Toshkent vaqti bilan) avtomatik ishga tushib, bittadan sifatli post chiqaradi.
- 🗂 **Takrorlanishning oldini olish**: Yuborilgan xabarlar `sent_posts.json` faylida saqlanadi.

---

## ⚙️ GitHub Secrets sozlamalari

GitHub repository sozlamalariga kirib (**Settings -> Secrets and variables -> Actions -> New repository secret**), quyidagilarni kiriting:

| Maxfiy kalit (Secret) | Tavsif | Majburiymi? |
| :--- | :--- | :--- |
| `BOT_TOKEN` | @BotFather orqali olingan Telegram Bot tokeni | Ha |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) orqali olingan Gemini API kaliti | Ha |
| `CHANNEL_ID` | Telegram kanal ID si yoki username (masalan: `@kosibiy`) | Yo'q (standart: `@kosibiy`) |

> ⚠️ **Muhim**: Botni o'z kanalingizga **Admin** qilib qo'shishni va unga xabar yuborish (Post Messages) huquqini berishni unutmang!

---

## 💻 Mahalliy kompyuterda ishga tushirish

1. Bog'liqliklarni o'rnating:
   ```bash
   pip install -r requirements.txt
   ```

2. Muhit o'zgaruvchilarini sozlang va botni ishga tushiring:
   ```bash
   export BOT_TOKEN="your_bot_token"
   export GEMINI_API_KEY="your_gemini_api_key"
   export CHANNEL_ID="@your_channel"
   python bot_poster.py
   ```
