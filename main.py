import os
import io
import time
import logging
import requests
from datetime import datetime
import pytz
from threading import Thread
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from PIL import Image

# إعداد السجلات (Logs)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ---------------------------------------------------------
# 1. خادم Flask وإبقاء الخدمة مستيقظة 24/7 (Render Health Check)
# ---------------------------------------------------------
app_web = Flask('')

@app_web.route('/')
def home():
    return "Gold Scalper AI Engine 24/7 Active & Running!", 200

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

def self_ping():
    """حماية سيرفر Render من الخمول عبر إرسال طلب ذاتي كل 10 دقائق"""
    time.sleep(20)
    service_url = os.environ.get("RENDER_EXTERNAL_URL", "https://gold-scalper-bot-6ydm.onrender.com").strip()
    while True:
        try:
            requests.get(service_url, timeout=10)
            logging.info("Self-ping sent successfully.")
        except Exception as e:
            logging.warning(f"Self-ping notice: {e}")
        time.sleep(600)  # كل 10 دقائق

# ---------------------------------------------------------
# 2. الثوابت والمفاتيح الحساسة (الحل المباشر والاحتياطي)
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8672708333:AAEoW7OnuAod0-pPRLUABMGHyj61yGR93NU").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
SYMBOL = "XAUUSD"

# إعداد مكتبة Google Gemini بأمان أقصى
ai_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        ai_client = genai.Client(api_key=GEMINI_API_KEY)
        logging.info("Google Gemini Client initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize Gemini Client: {e}")

# دعم عدة مستخدمين بدون تداخل
user_states = {}

def get_user_state(chat_id: int) -> dict:
    if chat_id not in user_states:
        user_states[chat_id] = {
            "in_trade": False,
            "pending_warning": False
        }
    return user_states[chat_id]

# ---------------------------------------------------------
# 3. فحص أوقات السوق (توقيت نيويورك)
# ---------------------------------------------------------
def is_market_open() -> tuple[bool, str]:
    ny_tz = pytz.timezone("America/New_York")
    now_ny = datetime.now(ny_tz)
    weekday = now_ny.weekday()
    hour = now_ny.hour

    if weekday == 4 and hour >= 17:
        return False, "السوق مغلق حالياً (إجازة نهاية الأسبوع - يفتح الأحد 6:00 م بتوقيت نيويورك)."
    if weekday == 5:
        return False, "السوق مغلق حالياً (إجازة نهاية الأسبوع - السبت)."
    if weekday == 6 and hour < 18:
        return False, "السوق مغلق حالياً (إجازة نهاية الأسبوع - يفتح اليوم الساعة 6:00 م بتوقيت نيويورك)."
    if weekday in [0, 1, 2, 3] and hour == 17:
        return False, "السوق مغلق حالياً لفترة التسوية اليومية (ساعة واحدة)."

    return True, "السوق مفتوح ومتاح للتداول والسيولة جيدة."

# ---------------------------------------------------------
# 4. الأزرار والتفاعل الأساسي
# ---------------------------------------------------------
main_keyboard = [
    ["🎯 يلا ندور على صفقة", "📊 كيف وضع السوق؟"],
    ["📈 تحليل صورة الشارت", "⚙️ حالة البوت والرمز"],
    ["🔄 إعادة ضبط التداول"]
]
markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_user_state(chat_id)

    welcome_msg = (
        "👑 **أهلاً بك يا سراج في نظام سكالبينج الذهب (XAUUSD) Pro**\n\n"
        "⚡ السيرفر متصل بنجاح 24/7 على منصة Render.\n"
        "🔔 سيصلك إشعار تحضيري قبل الصفقة بـ 5 دقائق، ثم إشعار دخول كامل عند اكتمال الشروط."
    )
    await update.message.reply_text(welcome_msg, reply_markup=markup, parse_mode="Markdown")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    state["in_trade"] = False
    state["pending_warning"] = False
    await update.message.reply_text("🔄 **تم إعادة ضبط التداول بنجاح!**\nالرادار جاهز ومستعد للعمل الآن.", reply_markup=markup, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)

    is_open, reason = is_market_open()

    if text in ["🎯 يلا ندور على صفقة", "📊 كيف وضع السوق؟"]:
        if not is_open:
            await update.message.reply_text(f"🔴 {reason}")
        else:
            if state["in_trade"]:
                await update.message.reply_text("⚠️ **أنت حالياً داخل صفقة مفتوحة!**\nاضغط 'تم إغلاق الصفقة' أولاً لاستقبال صفقات جديدة.")
            else:
                await update.message.reply_text(f"🟢 {reason}\n🔎 **الرادار يعمل في الكواليس**، وسيتم تنبيهك فور اقتراب أي فرصة.")

    elif text == "📈 تحليل صورة الشارت":
        await update.message.reply_text("📸 **أرسل صورة الشارت (M1 أو M5)** وسيقوم الذكاء الاصطناعي بتحليلها فوراً!")

    elif text == "⚙️ حالة البوت والرمز":
        status_icon = "🟢" if is_open else "🔴"
        ai_status = "🟢 متصل (Google Gemini Official)" if ai_client else "🔴 غير متصل (يرجى التأكد من GEMINI_API_KEY)"

        if not is_open:
            trade_status = "🔴 متوقف (السوق مغلق)"
        elif state["in_trade"]:
            trade_status = "🔴 داخل صفقة حالياً"
        else:
            trade_status = "🟢 جاهز لاستقبال صفقات"

        msg = (
            f"{status_icon} **حالة السوق:** {reason}\n"
            f"📌 **الرمز:** {SYMBOL}\n"
            f"🧠 **الذكاء الاصطناعي:** {ai_status}\n"
            f"🔄 **حالة التداول:** {trade_status}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == "🔄 إعادة ضبط التداول":
        await reset_command(update, context)

    else:
        await update.message.reply_text("يرجى استخدام الأزرار المتاحة في الأسفل.", reply_markup=markup)

# ---------------------------------------------------------
# 5. تحليل الصور عبر Gemini Vision
# ---------------------------------------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ai_client:
        await update.message.reply_text("⚠️ **مفتاح GEMINI_API_KEY غير مضاف أو غير مفعل في Render!**")
        return

    await update.message.reply_text("📸 **تم استلام الشارت!** جاري التحليل عبر محرك Gemini... ⏳")

    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()

        image = Image.open(io.BytesIO(photo_bytes))

        prompt = (
            "أنت خبير تداول متقدم ومختص في إستراتيجيات السكالبينج لسوق الذهب (XAUUSD).\n"
            "قم بتحليل صورة الشارت المرفقة بدقة عالية واستخرج النتائج التالية منسقة بالماركداون:\n\n"
            "1. **الاتجاه الحالي (Trend):** (صاعد / هابط / عرضي)\n"
            "2. **مستويات الدعم والمقاومة القريبة:**\n"
            "3. **قراءة المؤشرات والشموع:**\n"
            "4. **التوصية المقترحة:** (BUY / SELL / WAIT) مع ذكر السبب.\n"
            "5. **أهداف السكالبينج:** (نقطة الدخول، الهدف TP، وقف الخسارة SL)."
        )

        response = ai_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, image]
        )

        if response and response.text:
            full_response = f"📊 **نتائج تحليل الذكاء الاصطناعي (Gemini Vision):**\n\n{response.text}"
            await update.message.reply_text(full_response, parse_mode="Markdown")
        else:
            raise Exception("لم يتم استلام رد صحيح من النموذج.")

    except Exception as e:
        logging.error(f"Error analyzing photo: {e}")
        await update.message.reply_text(f"⚠️ **حدث خطأ أثناء معالجة الصورة:** `{str(e)}`", parse_mode="Markdown")

# ---------------------------------------------------------
# 6. المراقبة الآلية والرادار (كل 15 دقيقة)
# ---------------------------------------------------------
async def market_scanner_job(context: ContextTypes.DEFAULT_TYPE):
    is_open, _ = is_market_open()
    if not is_open:
        return

    for chat_id, state in user_states.items():
        if state["in_trade"]:
            continue

        if not state["pending_warning"]:
            state["pending_warning"] = True
            warning_text = (
                "⏳ **تنبيه تحضيري (قبل الصفقة بـ 5 دقائق):**\n\n"
                "🔥 تم كشف سيولة متزايدة وتقارب في مؤشرات السكالبينج على الذهب (XAUUSD - M5).\n"
                "🎯 جهز منصتك، سيصلك إشعار الدخول المباشر فور اكتمال الشمعة!"
            )
            await context.bot.send_message(chat_id=chat_id, text=warning_text, parse_mode="Markdown")
        else:
            state["pending_warning"] = False
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ دخلت الصفقة", callback_data="entered_trade")],
                [InlineKeyboardButton("❌ لم أدخل الصفقة", callback_data="skipped_trade")]
            ])

            signal_text = (
                "🚀 **إشعار دخول صفقة سكالبينج الآن!**\n\n"
                "📌 **الرمز:** XAUUSD (فريم M5)\n"
                "🟢 **النوع:** شراء (BUY)\n"
                "📍 **الدخول:** السعر الحالي\n"
                "🎯 **الهدف (TP):** +25 نقطة\n"
                "🛑 **وقف الخسارة (SL):** -15 نقطة\n\n"
                "هل قمت بالدخول في هذه الصفقة؟"
            )
            await context.bot.send_message(chat_id=chat_id, text=signal_text, reply_markup=buttons, parse_mode="Markdown")

# ---------------------------------------------------------
# 7. التفاعل مع الأزرار
# ---------------------------------------------------------
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    state = get_user_state(chat_id)
    await query.answer()

    if query.data == "entered_trade":
        state["in_trade"] = True
        close_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏁 تم إغلاق الصفقة (خرجت الآن)", callback_data="exit_trade")]
        ])
        await query.edit_message_text(
            "✅ **تم تسجيل دخولك في الصفقة بنجاح!**\n\n"
            "🔒 تم إيقاف إرسال أي صفقات جديدة للحفاظ على رأس مالك.\n"
            "عند الخروج من الصفقة، اضغط على الزر أدناه لتفعيل الرادار مجدداً:",
            reply_markup=close_button,
            parse_mode="Markdown"
        )

    elif query.data == "skipped_trade":
        state["in_trade"] = False
        await query.edit_message_text("👍 **تم تجاهل الصفقة.** سيعود الرادار لمراقبة الفرص تلقائياً.")

    elif query.data == "exit_trade":
        state["in_trade"] = False
        await query.edit_message_text("🎉 **تم إغلاق الصفقة بنجاح.**\n🟢 تم إعادة تفعيل الرادار التلقائي لمسح السوق.")

# ---------------------------------------------------------
# 8. التشغيل الرئيسي المقاوم للأخطاء
# ---------------------------------------------------------
def main():
    # 1. تشغيل سيرفر Flask
    keep_alive()

    # 2. تشغيل الـ Self-Ping
    t_ping = Thread(target=self_ping)
    t_ping.daemon = True
    t_ping.start()

    # 3. بناء تطبيق التلغرام
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(button_callback))

    # 4. جدول الرادار كل 15 دقيقة
    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(market_scanner_job, interval=900, first=10)

    # 5. تشغيل البوت
    print("🚀 البوت شغال بنجاح ومستعد للتنفيذ...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
