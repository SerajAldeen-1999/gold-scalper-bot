import os
import io
import time
import logging
import requests
from datetime import datetime
import pytz
from threading import Thread
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from PIL import Image

# ---------------------------------------------------------
# إعداد السجلات (Logs)
# ---------------------------------------------------------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ---------------------------------------------------------
# 1. خادم Flask وإبقاء الخدمة مستيقظة (Render Health Check)
# ---------------------------------------------------------
app_web = Flask('')

@app_web.route('/')
def home():
    return "Gold Scalper AI Engine 24/7 Active & Running!", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

def self_ping():
    time.sleep(20)
    service_url = os.environ.get("RENDER_EXTERNAL_URL", "https://gold-scalper-bot-6ydm.onrender.com").strip()
    while True:
        try:
            requests.get(service_url, timeout=10)
            logging.info("Self-ping sent successfully.")
        except Exception as e:
            logging.warning(f"Self-ping notice: {e}")
        time.sleep(600)

# ---------------------------------------------------------
# 2. الإعدادات والمتغيرات
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8672708333:AAHiWvvPzjx92vll3MZJhpRtbGNRauxLTSA").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "cf4c8efbc8604a818e7d7dc0379c8a12").strip()

SYMBOL = "XAU/USD"
user_states = {}

ai_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        logging.info("Gemini AI Client Ready.")
    except Exception as e:
        logging.error(f"Gemini Init Error: {e}")

def get_user_state(chat_id: int) -> dict:
    if chat_id not in user_states:
        user_states[chat_id] = {"in_trade": False, "radar_active": True}
    return user_states[chat_id]

# ---------------------------------------------------------
# 3. فحص أوقات سوق الذهب (XAU/USD)
# ---------------------------------------------------------
def is_market_open() -> tuple[bool, str]:
    ny_tz = pytz.timezone("America/New_York")
    now_ny = datetime.now(ny_tz)
    weekday = now_ny.weekday()
    hour = now_ny.hour

    if weekday == 4 and hour >= 17:
        return False, "السوق مغلق حالياً (إجازة نهاية الأسبوع)."
    if weekday == 5:
        return False, "السوق مغلق حالياً (السبت)."
    if weekday == 6 and hour < 18:
        return False, "السوق مغلق حالياً (يفتح الأحد 6:00 م بتوقيت نيويورك)."
    if weekday in [0, 1, 2, 3] and hour == 17:
        return False, "السوق مغلق لفترة التسوية اليومية."

    return True, "السوق مفتوح ومتاح للتداول."

# ---------------------------------------------------------
# 4. محرك جلب أسعار الذهب اللحظية
# ---------------------------------------------------------
def fetch_gold_price():
    try:
        url = f"https://api.twelvedata.com/price?symbol={SYMBOL}&apikey={TWELVE_DATA_API_KEY}"
        res = requests.get(url, timeout=10).json()
        if "price" in res:
            return float(res["price"])
        else:
            logging.error(f"TwelveData Error: {res}")
            return None
    except Exception as e:
        logging.error(f"Error fetching gold price: {e}")
        return None

# ---------------------------------------------------------
# 5. الرادار التلقائي في الكواليس (Job Queue)
# ---------------------------------------------------------
last_processed_price = None

async def gold_radar_job(context: ContextTypes.DEFAULT_TYPE):
    global last_processed_price
    is_open, _ = is_market_open()
    if not is_open:
        return

    current_price = fetch_gold_price()
    if current_price is None:
        return

    # فحص تغيّر السعر أو تحقق شروط التحليل
    if last_processed_price is not None:
        price_diff = current_price - last_processed_price
        # إذا تحرك السعر بأكثر من 1.5 دولار مثلاً، يرسل تنبيه
        if abs(price_diff) >= 1.5:
            direction = "🚀 صعود قوي" if price_diff > 0 else "🔻 هبوط سريع"
            msg = f"⚡️ **تنبيه حركة سريعة على الذهب ({SYMBOL})**\n\nالسعر الحالي: `{current_price}`\nالحركة: {direction} ({price_diff:+.2f}$)"
            
            # إرسال التنبيه لكل المستخدمين المسجلين
            for chat_id, state in user_states.items():
                if state.get("radar_active", True):
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
                    except Exception as e:
                        logging.error(f"Failed to send alert to {chat_id}: {e}")

    last_processed_price = current_price

# ---------------------------------------------------------
# 6. الأوامر والواجهة
# ---------------------------------------------------------
main_keyboard = [
    ["🎯 سعر الذهب اللحظي", "📊 كيف وضع السوق؟"],
    ["📈 تحليل صورة الشارت", "⚙️ حالة البوت والرمز"],
    ["🔄 إعادة ضبط التداول"]
]
markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_user_state(chat_id)
    await update.message.reply_text("👑 **أهلاً بك في نظام سكالبينج الذهب Pro**\n\nالرادار التلقائي يعمل الآن في الكواليس لتتبع الأسعار والصفقات 24/7.", reply_markup=markup, parse_mode="Markdown")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    state["in_trade"] = False
    await update.message.reply_text("🔄 **تم إعادة ضبط التداول بنجاح!**", reply_markup=markup, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    is_open, reason = is_market_open()

    if text == "🎯 سعر الذهب اللحظي":
        price = fetch_gold_price()
        if price:
            await update.message.reply_text(f"💰 **سعر الذهب الآن ({SYMBOL}):** `${price}`\n🟢 الرادار يفحص الحركة تلقائياً.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ متعذر جلب السعر حالياً، حاول مجدداً بعد قليل.")

    elif text == "📊 كيف وضع السوق؟":
        await update.message.reply_text(f"ℹ️ {reason}")

    elif text == "📈 تحليل صورة الشارت":
        await update.message.reply_text("📸 **أرسل صورة الشارت لتحليلها بواسطة الذكاء الاصطناعي!**")

    elif text == "⚙️ حالة البوت والرمز":
        status_icon = "🟢" if is_open else "🔴"
        ai_status = "🟢 متصل" if ai_client else "🔴 غير متصل"
        await update.message.reply_text(f"{status_icon} **السوق:** {reason}\n📌 **الرمز:** {SYMBOL}\n📡 **الرادار:** 🟢 شغال كل 60 ثانية\n🧠 **الذكاء الاصطناعي:** {ai_status}", parse_mode="Markdown")

    elif text == "🔄 إعادة ضبط التداول":
        await reset_command(update, context)

    else:
        await update.message.reply_text("يرجى استخدام الأزرار المتاحة.", reply_markup=markup)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ai_client:
        await update.message.reply_text("⚠️ **مفتاح GEMINI_API_KEY غير متصل!**")
        return
    await update.message.reply_text("📸 **جاري تحليل الشارت بالذكاء الاصطناعي... ⏳**")
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))
        prompt = "قم بتحليل الشارت المرفق واستخرج الاتجاه، والدعم/المقاومة، والتوصية."
        response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=[prompt, image])
        await update.message.reply_text(f"📊 **نتائج التحليل:**\n\n{response.text}", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ **خطأ:** `{str(e)}`", parse_mode="Markdown")

# ---------------------------------------------------------
# 7. التشغيل الرئيسي
# ---------------------------------------------------------
def main():
    keep_alive()
    t_ping = Thread(target=self_ping)
    t_ping.daemon = True
    t_ping.start()

    builder = Application.builder().token(BOT_TOKEN)
    application = builder.build()

    # تفعيل الرادار الدوري (يفحص السعر في الكواليس كل 60 ثانية)
    job_queue = application.job_queue
    job_queue.run_repeating(gold_radar_job, interval=60, first=10)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🚀 البوت والرادار شغالين بنجاح...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == '__main__':
    main()
