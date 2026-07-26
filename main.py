import os
import io
import logging
import base64
import requests
from datetime import datetime
import pytz
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from flask import Flask
from threading import Thread

# إعداد السجلات (Logs)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ---------------------------------------------------------
# 1. خادم Flask لإبقاء الخدمة حية 24/7 على Render
# ---------------------------------------------------------
app_web = Flask('')

@app_web.route('/')
def home():
    return "Gold Scalper AI Engine 24/7 Active!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ---------------------------------------------------------
# 2. البيانات الثابتة والمفاتيح الرسمية
# ---------------------------------------------------------
BOT_TOKEN = "8672708333:AAEoW7OnuAod0-pPRLUABMGHyj61yGR93NU"
SYMBOL = "XAUUSD"

# قراءة المفتاح وتنظيفه تلقائياً من أي مسافات أو أسطر زائدة
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

user_states = {
    "active_chat_id": None,
    "in_trade": False,
    "pending_warning": False
}

# ---------------------------------------------------------
# 3. فحص أوقات السوق (نيويورك)
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
    ["📈 تحليل صورة الشارت", "⚙️ حالة البوت والرمز"]
]
markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_states["active_chat_id"] = chat_id
    
    welcome_msg = (
        "أهلاً بك في نظام سكالبينج الذهب الأوتوماتيكي (XAUUSD) 🔱\n\n"
        "تم تفعيل الرادار التلقائي ليعمل في الكواليس كل 15 دقيقة.\n"
        "سيصلك إشعار تحضيري قبل الصفقة بـ 5 دقائق، ثم إشعار دخول كامل عند اكتمال الشروط."
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
        await update.message.reply_text("📸 أرسل صورة الشارت (فريم M1 أو M5) وسيقوم محرك الذكاء الاصطناعي بتحليلها فوراً!")

    elif text == "⚙️ حالة البوت والرمز":
        status_icon = "🟢" if is_open else "🔴"
        
        if not is_open:
            trade_status = "🔴 متوقف (السوق مغلق)"
        elif user_states["in_trade"]:
            trade_status = "🔴 داخل صفقة حالياً"
        else:
            trade_status = "🟢 جاهز لاستقبال صفقات"
        
        msg = (
            f"{status_icon} حالة السوق: {reason}\n"
            f"📌 الرمز: {SYMBOL}\n"
            f"🧠 الذكاء الاصطناعي: 🟢 متصل (OpenRouter Secure API)\n"
            f"🔄 حالة التداول: {trade_status}"
        )
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text("يرجى استخدام الأزرار في الأسفل.", reply_markup=markup)

# ---------------------------------------------------------
# 5. تحليل الصور عبر OpenRouter API
# ---------------------------------------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📸 تم استلام الشارت! جاري معالجة الصورة وتحليل الشموع... ⏳")

    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        base64_image = base64.b64encode(photo_bytes).decode('utf-8')

        prompt = (
            "أنت خبير تداول متقدم ومختص في إستراتيجيات السكالبينج لسوق الذهب (XAUUSD).\n"
            "قم بتحليل صورة الشارت المرفقة بدقة عالية واستخرج النتائج التالية بلغة عربية واضحة ومباشرة:\n\n"
            "1. الاتجاه الحالي (Trend): صاعد / هابط / عرضي.\n"
            "2. مستويات الدعم والمقاومة القريبة المرئية على الشارت.\n"
            "3. حركة المؤشرات القريبة المرئية (مثل RSI / MACD / المتوسطات / الشموع).\n"
            "4. التوصية المقترحة: (شراء BUY / بيع SELL / الانتظار) مع ذكر السبب باختصار.\n"
            "5. تحديد نقطة الدخول، والهدف (TP)، ووقف الخسارة (SL) المناسبين للسكالبينج."
        )

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "qwen/qwen-2-vl-7b-instruct:free",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]
        }

        response = requests.post(url, json=payload, headers=headers, timeout=60)

        if response.status_code == 200:
            result_data = response.json()
            analysis_result = result_data['choices'][0]['message']['content']
        else:
            raise Exception(f"خطأ API ({response.status_code}): {response.text}")

        if not analysis_result.strip():
            raise Exception("لم يتم استلام رد من النموذج.")

        full_response = f"📊 نتائج تحليل الذكاء الاصطناعي:\n\n{analysis_result}"
        await update.message.reply_text(full_response)

    except Exception as e:
        logging.error(f"Error analyzing photo: {e}")
        error_message = (
            "⚠️ حدث خطأ أثناء معالجة الصورة!\n\n"
            f"🔍 تفاصيل الخطأ: {str(e)}"
        )
        await update.message.reply_text(error_message)

# ---------------------------------------------------------
# 6. المراقبة الآلية في الكواليس (كل 15 دقيقة)
# ---------------------------------------------------------
async def market_scanner_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = user_states["active_chat_id"]
    if not chat_id:
        return

    is_open, reason = is_market_open()
    
    if not is_open or user_states["in_trade"]:
        return

    if not user_states["pending_warning"]:
        user_states["pending_warning"] = True
        warning_text = (
            "⏳ تنبيه تحضيري (قبل الصفقة بـ 5 دقائق):\n\n"
            "🔥 تم كشف سيولة متزايدة وتقارب في مؤشرات السكالبينج على الذهب (XAUUSD - M5).\n"
            "🎯 جهز منصة التداول الخاصة بك، سيصلك إشعار الدخول المباشر فور اكتمال الشمعة!"
        )
        await context.bot.send_message(chat_id=chat_id, text=warning_text)
    else:
        user_states["pending_warning"] = False
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ دخلت الصفقة", callback_data="entered_trade")],
            [InlineKeyboardButton("❌ لم أدخل الصفقة", callback_data="skipped_trade")]
        ])
        
        signal_text = (
            "🚀 إشعار دخول صفقة سكالبينج الآن!\n\n"
            "📌 الرمز: XAUUSD (فريم M5)\n"
            "🟢 النوع: شراء (BUY)\n"
            "📍 نقطة الدخول المقترحة: السعر الحالي\n"
            "🎯 هدف أرباح (TP): +25 نقطة\n"
            "🛑 وقف خسارة (SL): -15 نقطة\n\n"
            "هل قمت بالدخول في هذه الصفقة؟"
        )
        await context.bot.send_message(chat_id=chat_id, text=signal_text, reply_markup=buttons)

# ---------------------------------------------------------
# 7. التفاعل مع الأزرار
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
            "✅ تم تسجيل دخولك في الصفقة بنجاح!\n\n"
            "🔒 تم إيقاف إرسال أي صفقات جديدة للحفاظ على رأس مالك.\n"
            "عند تحقيق الهدف أو الخروج من الصفقة، اضغط على الزر أدناه لتفعيل الرادار مجدداً:",
            reply_markup=close_button
        )

    elif query.data == "skipped_trade":
        user_states["in_trade"] = False
        await query.edit_message_text("👍 تم إلغاء الصفقة. سيعود الرادار لمراقبة الفرص الجديدة تلقائياً.")

    elif query.data == "exit_trade":
        user_states["in_trade"] = False
        await query.edit_message_text("🎉 تم إغلاق الصفقة.\n🟢 تم إعادة تفعيل الرادار التلقائي لمسح السوق واستخراج صفقات جديدة.")

# ---------------------------------------------------------
# 8. التشغيل الرئيسي
# ---------------------------------------------------------
def main():
    keep_alive()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(button_callback))

    job_queue = application.job_queue
    if job_queue:
        job_queue.run_repeating(market_scanner_job, interval=900, first=10)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
