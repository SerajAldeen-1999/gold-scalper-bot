import os
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask
from threading import Thread

# إعداد السجلات لمتابعة الأخطاء إن وجدت
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# إعداد خادم Flask لإبقاء التطبيق حياً على Render
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

# توكن البوت
BOT_TOKEN = "8672708333:AAFLEBR1AwNWHPMAa9SzXyOl8Gk9nsgMLjg"

# لوحة الأزرار
main_keyboard = [
    ["🎯 يلا ندور على صفقة", "📊 كيف وضع السوق؟"],
    ["📈 تحليل صورة الشارت", "⚙️ حالة البوت والرمز"]
]
markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك في بوت سكالبينج الذهب 🔱\nاختر من الأزرار بالأسفل:", reply_markup=markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🎯 يلا ندور على صفقة":
        await update.message.reply_text("🟢 السوق مفتوح، أرسل صورة الشارت للتحليل.")
    elif text == "📊 كيف وضع السوق؟":
        await update.message.reply_text("📊 السوق يعمل وجاهز لاستقبال الشارتات.")
    elif text == "📈 تحليل صورة الشارت":
        await update.message.reply_text("📸 أرسل صورة الشارت الآن لفحصها.")
    elif text == "⚙️ حالة البوت والرمز":
        await update.message.reply_text("🟢 البوت يعمل بنجاح 24/7 على سيرفرات Render.")
    else:
        await update.message.reply_text("يرجى استخدام الأزرار الموجودة في الأسفل.", reply_markup=markup)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 تم استلام الصورة بنجاح! جاري المعالجة...")

def main():
    # بدء خادم الويب أولاً
    keep_alive()
    
    # بناء تطبيق التليجرام
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # تشغيل البوت بالطريقة المباشرة
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
