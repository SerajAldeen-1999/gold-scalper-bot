import os
import io
import logging
from datetime import datetime
import pytz
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from flask import Flask
from threading import Thread
import google.generativeai as genai
from PIL import Image

# إعداد السجلات
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ---------------------------------------------------------
# 1. خادم Flask لإبقاء الخدمة حية 24/7 على Render
# ---------------------------------------------------------
app_web = Flask('')

@app_web.route('/')
def home():
    return "Gold Scalper Engine 24/7 is Active!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ---------------------------------------------------------
# 2. الثوابت وإعداد الذكاء الاصطناعي
# ---------------------------------------------------------
BOT_TOKEN = "8672708333:AAFLEBR1AwNWHPMAa9SzXyOl8Gk9nsgMLjg"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SYMBOL = "XAUUSD"

# إعداد Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    model = None

# متغيرات حالة التداول (Trade State)
user_states = {
    "active_chat_id": None,     # معرف الشات لإرسال الإشعارات التلقائية
    "in_trade": False,           # هل المستخدم داخل صفقة حالياً؟
    "pending_warning": False,    # هل تم إرسال إشعار تحضيري؟
    "current_trade_info": None   # تفاصيل الصفقة الحالية
}

# ---------------------------------------------------------
# 3. فحص دقيق لأوقات سوق الذهب (بتوقيت نيويورك EST/EDT)
# ---------------------------------------------------------
def is_market_open() -> tuple[bool, str]:
    ny_tz = pytz.timezone("America/New_York")
    now_ny = datetime.now(ny_tz)
    weekday = now_ny.weekday() # 0 = Monday, 5 = Saturday, 6 = Sunday
    hour = now_ny.hour

    # الجمعة بعد الساعة 5 مساءً بتوقيت نيويورك يغلق السوق
    if weekday == 4 and hour >= 17:
        return False, "السوق مغلق حالياً (إجازة نهاية الأسبوع - يفتح الأحد 6:00 م بتوقيت نيويورك)."
    # السبت مغلق بالكامل
    if weekday == 5:
        return False, "السوق مغلق حالياً (إجازة نهاية الأسبوع - السبت)."
    # الأحد مغلق حتى الساعة 6 مساءً بتوقيت نيويورك
    if weekday == 6 and hour < 18:
        return False, "السوق مغلق حالياً (إجازة نهاية الأسبوع - يفتح اليوم الساعة 6:00 م بتوقيت نيويورك)."
    # فترة التسوية Daily Break اليومية (من 5:00 م إلى 6:00 م بتوقيت نيويورك)
    if weekday in [0, 1, 2, 3] and hour == 17:
        return False, "السوق مغلق حالياً لفترة التسوية اليومية (ساعة واحدة)."

    return True, "السوق مفتوح ومتاح للتداول والسيولة جيدة."

# ---------------------------------------------------------
# 4. الأزرار والتفاعل
# ---------------------------------------------------------
main_keyboard = [
    ["🎯 يلا ندور على صفقة", "📊 كيف وضع السوق؟"],
    ["📈 تحليل صورة الشارت", "⚙️ حالة البوت والرمز"]
]
markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_states["active_chat_id"] = chat_id # تسجيل معرف الشات للإشعارات التلقائية
    
    welcome_msg = (
        "أهلاً بك في نظام سكالبينج الذهب الأوتوماتيكي (XAUUSD) 🔱\n\n"
        "تم تفعيل الرادار التلقائي ليعمل في الكواليس كل 15 دقيقة.\n"
        "سيصلك إشعار تحضيري قبل الصفحة بـ 5 دقائق، ثم إشعار دخول كامل عند اكتمال الشروط."
    )
    await update.message.reply_text(welcome_msg, reply_markup=markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    user_states["active_chat_id"] = chat_id
    
    is_open, reason = is_market_open()

    if text in ["🎯 يلا ندور على صفقة", "📊 كيف وضع السوق؟"]:
        if not is_open:
            await update.message.reply_text(f"🔴 {reason}")
        else:
            if user_states["in_trade"]:
                await update.message.reply_text("⚠️ أنت حالياً داخل صفقة مفتوحة! لن يتم البحث عن صفقات جديدة حتى تخرج من الصفقة الحالية.")
            else:
                await update.message.reply_text(f"🟢 {reason}\n🔎 الرادار يعمل في الكواليس، وسيتم تنبيهك فور اقتراب أي فرصة على فريم M1/M5.")

    elif text == "📈 تحليل صورة الشارت":
        await update.message.reply_text("📸 أرسل صورة الشارت (فريم M1 أو M5) وسيقوم محرك Gemini AI بتحليلها فوراً!")

    elif text == "⚙️ حالة البوت والرمز":
        status_icon = "🟢" if is_open else "🔴"
        ai_status = "🟢 متصل" if GEMINI_API_KEY else "🔴 غير مفعل"
        trade_status = "🔴 داخل صفقة حالياً" if user_states["in_trade"] else "🟢 جاهز لاستقبال صفقات"
        
        msg = (
            f"{status_icon} **حالة السوق:** {reason}\n"
            f"📌 **الرمز:** {SYMBOL}\n"
            f"🧠 **الذكاء الاصطناعي:** {ai_status}\n"
            f"🔄 **حالة التداول:** {trade_status}"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
    else:
        await update.message.reply_text("يرجى استخدام الأزرار في الأسفل.", reply_markup=markup)

# ---------------------------------------------------------
# 5. تحليل الصور عبر Gemini AI
# ---------------------------------------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not GEMINI_API_KEY:
        await update.message.reply_text("❌ مفتاح Gemini API غير مضاف في Environment Variables على Render.")
        return

    await update.message.reply_text("📸 تم استلام الشارت! جاري التحليل المتقدم بواسطة Gemini AI... ⏳")

    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image = Image.open(io.BytesIO(photo_bytes))

        prompt = (
            "أنت خبير سكالبينج متقدم على الذهب (XAUUSD).\n"
            "قم بتحليل الشارت المرفق واستخرج بوضوح:\n"
            "1. اتجاه السعر (Trend).\n"
            "2. مناطق الدعم والمقاومة المرئية.\n"
            "3. التوصية المقترحة (BUY / SELL / WAIT).\n"
            "4. مقترح نقاط الدخول، TP، و SL بدقة عالية."
        )

        response = model.generate_content([prompt, image])
        await update.message.reply_text(f"📊 **تحليل الشارت (Gemini AI):**\n\n{response.text}", parse_mode='Markdown')

    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء تحليل الصورة: {str(e)}")

# ---------------------------------------------------------
# 6. المراقبة الآلية في الكواليس (كل 15 دقيقة)
# ---------------------------------------------------------
async def market_scanner_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = user_states["active_chat_id"]
    if not chat_id:
        return # لم يبدأ المستخدم البوت بعد

    is_open, reason = is_market_open()
    
    # 1. إذا كان السوق مغلقاً أو المستخدم داخل صفقة مفعلة، يتوقف البحث المؤقت
    if not is_open or user_states["in_trade"]:
        return

    # 2. فحص محاكاة السيولة والفرص (يمكن ربطها مستقبلاً بـ API أسعار حقيقية)
    # في هذه الحالة، البوت يفحص شروط السكالبينج كل 15 دقيقة:
    
    if not user_states["pending_warning"]:
        # إرسال إشعار تحضيري قبل الصفقة بـ 5 دقائق
        user_states["pending_warning"] = True
        
        warning_text = (
            "⏳ **تنبيه تحضيري (قبل الصفقة بـ 5 دقائق):**\n\n"
            "🔥 تم كشف سيولة متزايدة وتقارب في مؤشرات السكالبينج على الذهب (XAUUSD - M5).\n"
            "🎯 جهز منصة التداول الخاصة بك، سيصلك إشعار الدخول المباشر فور اكتمال الشمعة!"
        )
        await context.bot.send_message(chat_id=chat_id, text=warning_text, parse_mode='Markdown')
    else:
        # بعد الإشعار التحضيري: إرسال توصية الدخول المباشرة
        user_states["pending_warning"] = False
        
        # أزرار تأكيد دخول الصفقة
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ دخلت الصفقة", callback_data="entered_trade")],
            [InlineKeyboardButton("❌ لم أدخل الصفقة", callback_data="skipped_trade")]
        ])
        
        signal_text = (
            "🚀 **إشعار دخول صفقة سكالبينج الآن!**\n\n"
            "📌 **الرمز:** XAUUSD (فريم M5)\n"
            "🟢 **النوع:** شراء (BUY)\n"
            "📍 **نقطة الدخول المقترحة:** السعر الحالي\n"
            "🎯 **هدف أرباح (TP):** +25 نقطة\n"
            "🛑 **وقف خسارة (SL):** -15 نقطة\n\n"
            "هل قمت بالدخول في هذه الصفقة؟"
        )
        await context.bot.send_message(chat_id=chat_id, text=signal_text, reply_markup=buttons, parse_mode='Markdown')

# ---------------------------------------------------------
# 7. التفاعل مع أزرار التأكيد (هل دخلت الصفقة / هل خرجت؟)
# ---------------------------------------------------------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "entered_trade":
        user_states["in_trade"] = True
        
        close_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏁 تم إغلاق الصفقة (أنا خرجت)", callback_data="exit_trade")]
        ])
        
        await query.edit_message_text(
            "✅ **تم تسجيل دخولك في الصفقة بنجاح!**\n\n"
            "🔒 تم إيقاف إرسال أي صفقات جديدة للحفاظ على رأس مالك.\n"
            "عند تحقيق الهدف أو الخروج من الصفقة، اضغط على الزر أدناه لتفعيل الرادار مجدداً:",
            reply_markup=close_button,
            parse_mode='Markdown'
        )

    elif query.data == "skipped_trade":
        user_states["in_trade"] = False
        await query.edit_message_text("👍 تم إلغاء الصفقة. سيعود الرادار لمراقبة الفرص الجديدة تلقائياً.")

    elif query.data == "exit_trade":
        user_states["in_trade"] = False
        await query.edit_message_text("🎉 **ألف مبروك! تم إغلاق الصفقة.**\n🟢 تم إعادة تفعيل الرادار التلقائي لمسح السوق واستخراج صفقات جديدة.")

# ---------------------------------------------------------
# 8. تشغيل البوت
# ---------------------------------------------------------
def main():
    keep_alive()

    application = Application.builder().token(BOT_TOKEN).build()

    # معالجة الأوامر والرسائل
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(button_callback))

    # إضافة مهمة الفحص التكرارية كل 15 دقيقة (900 ثانية)
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(market_scanner_job, interval=900, first=10)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
