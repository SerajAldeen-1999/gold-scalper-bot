import os
import io
import asyncio
from datetime import datetime
import pytz
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask
from threading import Thread
import google.generativeai as genai
from PIL import Image

# 1. إعداد خادم إبقاء الخدمة حية 24/7 على Render
app_web = Flask('')

@app_web.route('/')
def home():
    return "Bot is running 24/7 with Gemini AI!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# 2. قراءة المفاتيح المحمية من بيئة التشغيل
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SYMBOL = "XAUUSD"

# تهيئة مكتبة Google Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

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
    welcome_msg = "أهلاً بك في منظومة سكالبينج الذهب (XAUUSD) المدعومة بالذكاء الاصطناعي Gemini 🔱\nاختر من الأزرار بالأسفل:"
    await update.message.reply_text(welcome_msg, reply_markup=markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    is_open, reason = is_market_open()
    
    if text in ["🎯 يلا ندور على صفقة", "📊 كيف وضع السوق؟"]:
        if not is_open:
            await update.message.reply_text(f"🔴 {reason}")
        else:
            await update.message.reply_text("🟢 السوق مفتوح! يمكنك إرسال صورة الشارت الآن لتحليل الفرص والسيولة بالذكاء الاصطناعي.")
    elif text == "📈 تحليل صورة الشارت":
        await update.message.reply_text("📸 أرسل صورة الشارت (فريم M1 أو M5) وسيقوم الذكاء الاصطناعي Gemini بفحصها فوراً!")
    elif text == "⚙️ حالة البوت والرمز":
        status_icon = "🟢" if is_open else "🔴"
        await update.message.reply_text(f"{status_icon} البوت يعمل بنجاح 24/7.\n📌 الرمز: {SYMBOL}\n🧠 الذكاء الاصطناعي: Gemini Flash متصل\n⚪️ حالة السوق: {reason}")
    else:
        await update.message.reply_text("يرجى استخدام الأزرار بالأسفل.", reply_markup=markup)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 تم استلام صورة الشارت! جاري التحليل بواسطة محرك Gemini للذكاء الاصطناعي... ⏳")
    
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))
        
        prompt = (
            "أنت خبير تداول متقدم ومختص في إستراتيجيات السكالبينج لسوق الذهب (XAUUSD).\n"
            "قم بتحليل صورة الشارت المرفقة بدقة عالية واستخرج ما يلي بلغة عربية واضحة ومباشرة:\n\n"
            "1. الاتجاه الحالي (Trend): صاعد / هابط / عرضي.\n"
            "2. أهم مستويات الدعم والمقاومة القريبة المرئية في الشارت.\n"
            "3. نمط الشموع أو الهيكل الملاحظ (مثل: ارتداد، كسر، نموذج فني).\n"
            "4. توصية سكالبينج واضحة (شراء BUY / بيع SELL / الانتظار).\n"
            "5. تحديد مقترح لنقطة الدخول، الهدف (TP)، ووقف الخسارة (SL).\n\n"
            "اجعل الإجابة مرتبة في نقاط واضحة ومختصرة لتناسب التداول السريع."
        )
        
        response = model.generate_content([prompt, image])
        await update.message.reply_text(f"📊 **نتائج تحليل الذكاء الاصطناعي (Gemini):**\n\n{response.text}", parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء تحليل الصورة: {str(e)}\nيرجى إعادة المحاولة بصورة أوضح.")

if __name__ == '__main__':
    keep_alive()
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("جاري تشغيل البوت الذكي على Render 24/7...")
    app.run_polling()
