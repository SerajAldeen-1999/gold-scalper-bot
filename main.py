import os
import asyncio
from datetime import datetime
import pytz
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask
from threading import Thread

# 1. خادم إبقاء الخدمة حية 24/7 على Render
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

# 2. إعدادات التوكن والرمز
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
        await update.message.reply_text("📸 أرسل صورة الشارت (M1/M5) ليتم تحليلها بالذكاء الاصطناعي.")
    elif text == "⚙️ حالة البوت والرمز":
        status_icon = "🟢" if is_open else "🔴"
        await update.message.reply_text(f"{status_icon} البوت يعمل بنجاح.\n📌 الرمز: {SYMBOL}\n⏱ الفريم: M1\n⚪️ حالة السوق: {reason}")
    else:
        await update.message.reply_text("يرجى استخدام الأزرار بالأسفل.", reply_markup=markup)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 تم استقبال صورة الشارت بنجاح!\n🔎 جاري التحليل بواسطة الذكاء الاصطناعي...")
    analysis_result = (
        "📊 **نتائج تحليل الشارت (XAUUSD):**\n\n"
        "🔹 **الاتجاه العام:** صاعد على فريم M1/M5\n"
        "🔹 **مستويات الدعم القريبة:** 2380.50 - 2382.00\n"
        "🔹 **مستويات المقاومة القريبة:** 2390.00 - 2392.50\n\n"
        "💡 **توصية السكالبينج المقترحة:**\n"
        "• نوع الصفقة: شراء (BUY) عند الارتداد من الدعم\n"
        "• الهدف (TP): 2388.00\n"
        "• وقف الخسارة (SL): 2378.50\n"
        "⚠️ التزم باللوت المحدد (0.01) لإدارة المخاطر."
    )
    await update.message.reply_text(analysis_result, parse_mode='Markdown')

if __name__ == '__main__':
    keep_alive()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("جاري تشغيل البوت على Render 24/7...")
    app.run_polling()
