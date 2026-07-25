import os
import asyncio
from datetime import datetime
import pytz
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask
from threading import Thread

# 1. إعداد خادم إبقاء الخدمة حية 24/7 على Render
app_web = Flask('')

@app_web.route('/')
def home():
    return "Bot is running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# 2. إعداد مفتاح التلجرام والرمز
BOT_TOKEN = "8672708333:AAFLEBR1AwNWHPMAa9SzXyOl8Gk9nsgMLjg"
SYMBOL = "XAUUSD"

# 3. فحص أوقات السوق
def is_market_open() -> tuple[bool, str]:
    ny_tz = pytz.timezone("America/New_York")
    now_ny = datetime.now(ny_tz)
    weekday = now_ny.weekday()
    hour = now_ny.hour

    if weekday == 5:
        return False, "السوق مغلق حالياً بسبب إجازة نهاية الأسبوع (السبت)."
    if weekday == 6 and hour < 18:
        return False, "السوق مغلق حالياً بسبب إجازة نهاية الأسبوع (يفتح الأحد 6:00 مساءً بتوقيت نيويورك)."
    if weekday == 4 and hour >= 17:
        return False, "السوق مغلق حالياً لإجازة نهاية الأسبوع."
    if hour == 17:
        return False, "السوق مغلق حالياً لفترة التسوية اليومية."

    return True, "السوق مفتوح ومتاح للتداول."

# 4. لوحة الأزرار الرئيسية
main_keyboard = [
    ["🎯 يلا ندور على صفقة", "📊 كيف وضع السوق؟"],
    ["📈 تحليل صورة الشارت", "⚙️ حالة البوت والرمز"]
]
markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_msg = "أهلاً بك في منظومة سكالبينج الذهب (XAUUSD) 🔱\nاختر من الأزرار بالأسفل:"
    await update.message.reply_text(welcome_msg, reply_markup=markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    is_open, reason = is_market_open()
    
    if text in ["🎯 يلا ندور على صفقة", "📊 كيف وضع السوق؟"]:
        if not is_open:
            await update.message.reply_text(f"🔴 {reason}")
        else:
            await update.message.reply_text("🟢 السوق مفتوح! جاري فحص الفرص والسيولة...")
    elif text == "📈 تحليل صورة الشارت":
        await update.message.reply_text("📸 أرسل صورة الشارت (فريم M1 أو M5) ليتم تحليلها.")
    elif text == "⚙️ حالة البوت والرمز":
        status_icon = "🟢" if is_open else "🔴"
        await update.message.reply_text(f"{status_icon} البوت يعمل بنجاح 24/7.\n📌 الرمز: {SYMBOL}\n⚪️ حالة السوق: {reason}")
    else:
        await update.message.reply_text("يرجى استخدام الأزرار بالأسفل.", reply_markup=markup)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 تم استلام صورة الشارت بنجاح!\n🔎 جاري فحص النموذج الهيكلي والمستويات...")

if __name__ == '__main__':
    keep_alive()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("جاري تشغيل البوت على Render 24/7...")
    app.run_polling()
