import os
import io
import time
import base64
import logging
import requests
import json
from datetime import datetime
import pytz
from threading import Thread
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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
    return "Gold Scalper Pro AI Engine 24/7 Active & Running!", 200

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
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "").strip()

SYMBOL = "XAU/USD"
SL_BUFFER_PRICE = 3.0  # هامش الأمان لوقف الخسارة (3 دولار)
user_states = {}

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
        return False, "السوق مغلق حالياً لفترة التسوية اليومية (Daily Rollover)."

    return True, "السوق مفتوح ومتاح للتداول."

# ---------------------------------------------------------
# 4. جلب أسعار الذهب اللحظية
# ---------------------------------------------------------
def fetch_gold_price():
    try:
        if not TWELVE_DATA_API_KEY:
            return None
        url = f"https://api.twelvedata.com/price?symbol={SYMBOL}&apikey={TWELVE_DATA_API_KEY}"
        res = requests.get(url, timeout=10).json()
        if "price" in res:
            return float(res["price"])
        else:
            return None
    except Exception as e:
        logging.error(f"Error fetching gold price: {e}")
        return None

# ---------------------------------------------------------
# 5. جلب صورة شارت حية تلقائياً (M5 Chart Image)
# ---------------------------------------------------------
def fetch_live_chart_image():
    try:
        chart_url = "https://chart-img.com/v1/tradingview/advanced-chart?symbol=OANDA:XAUUSD&interval=5m&theme=dark&width=800&height=600"
        response = requests.get(chart_url, timeout=15)
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        logging.error(f"Error fetching live chart image: {e}")
        return None

# ---------------------------------------------------------
# 6. الرادار التلقائي (كل 15 دقيقة)
# ---------------------------------------------------------
async def gold_radar_job(context: ContextTypes.DEFAULT_TYPE):
    is_open, _ = is_market_open()
    if not is_open:
        return

    current_price = fetch_gold_price()
    if current_price is None:
        return

    msg = f"📡 **تحديث رادار الذهب التلقائي (كل 15 دقيقة)**\n\nالسعر الحالي للذهب: `{current_price}`\nاختر من الأزرار الأدناه نوع التوصية التي تريدها فوراً!"
    
    for chat_id, state in user_states.items():
        if state.get("radar_active", True):
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            except Exception as e:
                logging.error(f"Failed to send radar alert to {chat_id}: {e}")

# ---------------------------------------------------------
# 7. الواجهة والأوامر (جميع الخيارات بدون تكرار)
# ---------------------------------------------------------
main_keyboard = [
    ["⚡️ توصية فورية (Market)", "⏳ أمر معلق (Limit Order)"],
    ["🎯 سعر الذهب اللحظي", "📈 تحليل شارت M1 / M5"],
    ["📊 كيف وضع السوق؟", "⚙️ حالة البوت والرمز"],
    ["🔄 إعادة ضبط التداول"]
]
markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_user_state(chat_id)
    await update.message.reply_text(
        "👑 **أهلاً بك في نظام توصيات سكالبينج الذهب المطور**\n\n"
        "• **توصية فورية / معلقة تلقائية** دون الحاجة لرفع صورة.\n"
        "• **خيارات قراءة الشارت المخصصة (M1 / M5)** عند رفع صورة.\n"
        "• **رسائل نسخ سريع ومباشر** بنقرة واحدة لتسريع التنفيذ.",
        reply_markup=markup, parse_mode="Markdown"
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    state.pop("exec_mode", None)
    await update.message.reply_text("🔄 **تم إعادة ضبط التداول بنجاح!**", reply_markup=markup, parse_mode="Markdown")

# ---------------------------------------------------------
# 8. محرك التحليل والذكاء الاصطناعي
# ---------------------------------------------------------
async def process_and_analyze_image(update: Update, photo_bytes: bytes, execution_type: str = "MARKET"):
    try:
        base64_image = base64.b64encode(photo_bytes).decode('utf-8')

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        mode_text = "توصية بسعر السوق (Market Execution)" if execution_type == "MARKET" else "أمر معلق (Pending Limit Order)"
        
        system_prompt = (
            f"أنت خبير ومدير مخاطر محترف في تداول الذهب (XAU/USD).\n"
            f"نوع التنفيذ المطلوب لهذه التحليلات هو: {mode_text}.\n"
            "حلل الشارت المرفق مع تطبيق القواعد التالية:\n"
            "1. فحص اتجاه فريم الساعة (H1): إذا كان صاعداً يمنع البيع، وإذا كان هابطاً يمنع الشراء.\n"
            "2. إذا كان نوع التنفيذ 'MARKET'، اقترح سعر دخول فوري وقريب مع أهداف وستوب مدروس.\n"
            "3. إذا كان نوع التنفيذ 'LIMIT'، اقترح سعراً معلقاً مثالياً (BUY LIMIT أو SELL LIMIT) من مناطق دعم أو مقاومة قوية.\n"
            "4. حدد الهدف الأول (TP1) بشكل قريب للسكالبينج (2$ إلى 2.5$) والهدف الثاني (TP2) متوسعاً (4$ إلى 5$).\n"
            "5. أخرج الرد بتنسيق JSON حصراً بدون أي نص إضافي خارجه:\n"
            "{\n"
            '  "action": "BUY" أو "SELL" أو "BUY_LIMIT" أو "SELL_LIMIT" أو "WAIT",\n'
            '  "entry": 4026.50,\n'
            '  "tp1": 4028.50,\n'
            '  "tp2": 4031.50,\n'
            '  "sl": 4023.50,\n'
            '  "rr": "1:1.8",\n'
            '  "note": "سبب القرار في سطر واحد"\n'
            "}"
        )

        payload = {
            "model": "google/gemini-2.5-flash",
            "max_tokens": 450,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": system_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ]
        }
        
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30).json()
        
        if "choices" in response and len(response["choices"]) > 0:
            content = response["choices"][0]["message"]["content"].strip()
            clean_json = content.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_json)

            action = data.get("action", "WAIT")
            entry = data.get("entry", 0.0)
            tp1 = data.get("tp1", 0.0)
            tp2 = data.get("tp2", 0.0)
            sl_raw = data.get("sl", 0.0)
            rr = data.get("rr", "1:1.5")
            note = data.get("note", "")

            if action in ["BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT"]:
                if "BUY" in action:
                    adjusted_sl = round(sl_raw - SL_BUFFER_PRICE, 2)
                else:
                    adjusted_sl = round(sl_raw + SL_BUFFER_PRICE, 2)

                text_msg = (
                    f"🚨 **توصية سكالبينج ذهبية ({action}):**\n\n"
                    f"• نوع التنفيذ: **{action}**\n"
                    f"• سعر الدخول المقترح: `{entry}`\n"
                    f"🎯 **الهدف الأول (TP1):** `{tp1}` (جني أرباح وتأمين)\n"
                    f"🚀 **الهدف الثاني (TP2):** `{tp2}` (هدف متوسع)\n"
                    f"🛡️ **وقف الخسارة (SL المعدل):** `{adjusted_sl}`\n"
                    f"• نسبة المخاطرة للعائد: `{rr}`\n\n"
                    f"💡 **التحليل:** {note}\n"
                    f"───────────────\n"
                    f"🛡️ **قاعدة التأمين (Breakeven):** عند وصول السعر للهدف الأول (TP1)، انقُل الستوب فوراً لسعر الدخول `{entry}`."
                )

                copy_block = (
                    f"📋 **بيانات النسخ السريع للصفقة (اضغط للنسخ):**\n\n"
                    f"```text\n"
                    f"Type: {action}\n"
                    f"Entry: {entry}\n"
                    f"TP1: {tp1}\n"
                    f"TP2: {tp2}\n"
                    f"SL: {adjusted_sl}\n"
                    f"```"
                )

                await update.message.reply_text(text_msg, parse_mode="Markdown")
                await update.message.reply_text(copy_block, parse_mode="Markdown")

            else:
                text_msg = (
                    f"🎯 **توصية سكالبينج (XAU/USD):**\n\n"
                    f"• التوصية: **انتظار (WAIT)**\n"
                    f"💡 **السبب:** {note}"
                )
                await update.message.reply_text(text_msg, parse_mode="Markdown")

        else:
            await update.message.reply_text(f"⚠️ خطأ من المزود الذكي: {str(response)}")

    except Exception as e:
        await update.message.reply_text(f"⚠️ حدث خطأ أثناء معالجة التحليل: {str(e)}")

# ---------------------------------------------------------
# 9. معالجة الرسائل والأزرار
# ---------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    is_open, reason = is_market_open()

    if text == "⚡️ توصية فورية (Market)":
        if not is_open:
            await update.message.reply_text(f"🚫 **السوق مغلق حالياً!**\nℹ️ {reason}")
            return
        state["exec_mode"] = "MARKET"
        await update.message.reply_text("⚡️ **جاري استخراج توصية فورية تلقائية من الشارت اللحظي... ⏳**")
        
        chart_bytes = fetch_live_chart_image()
        if chart_bytes:
            await process_and_analyze_image(update, chart_bytes, execution_type="MARKET")
        else:
            await update.message.reply_text("⚠️ متعذر جلب بيانات الشارت تلقائياً. يمكنك رفع صورة الشارت عبر خيار '📈 تحليل شارت M1 / M5'.")

    elif text == "⏳ أمر معلق (Limit Order)":
        if not is_open:
            await update.message.reply_text(f"🚫 **السوق مغلق حالياً!**\nℹ️ {reason}")
            return
        state["exec_mode"] = "LIMIT"
        await update.message.reply_text("⏳ **جاري حساب نقاط الأمر المعلق (Limit) تلقائياً... ⏳**")
        
        chart_bytes = fetch_live_chart_image()
        if chart_bytes:
            await process_and_analyze_image(update, chart_bytes, execution_type="LIMIT")
        else:
            await update.message.reply_text("⚠️ متعذر جلب بيانات الشارت تلقائياً. يمكنك رفع صورة الشارت عبر خيار '📈 تحليل شارت M1 / M5'.")

    elif text == "📈 تحليل شارت M1 / M5":
        await update.message.reply_text("📸 **أرسل الآن صورة الشارت (سواء بفريم الدقيقة M1 أو 5 دقائق M5) لنقوم بتحليلها فوراً...**")

    elif text == "🎯 سعر الذهب اللحظي":
        price = fetch_gold_price()
        if price:
            await update.message.reply_text(f"💰 **سعر الذهب الآن ({SYMBOL}):** `${price}`\n🟢 الرادار يعمل بانتظام.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ متعذر جلب السعر حالياً.")

    elif text == "📊 كيف وضع السوق؟":
        await update.message.reply_text(f"ℹ️ {reason}")

    elif text == "⚙️ حالة البوت والرمز":
        status_icon = "🟢" if is_open else "🔴"
        ai_status = "🟢 متصل (نظام M1/M5 Mapped)" if OPENROUTER_API_KEY else "🔴 غير متصل"
        await update.message.reply_text(f"{status_icon} **السوق:** {reason}\n📌 **الرمز:** {SYMBOL}\n📡 **الرادار:** 🟢 شغال\n🧠 **الذكاء الاصطناعي:** {ai_status}", parse_mode="Markdown")

    elif text == "🔄 إعادة ضبط التداول":
        await reset_command(update, context)

    else:
        await update.message.reply_text("يرجى استخدام الأزرار المتاحة أدناه.", reply_markup=markup)

# ---------------------------------------------------------
# 10. معالجة الصور المرفوعة يدوياً (M1 / M5)
# ---------------------------------------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_open, reason = is_market_open()
    if not is_open:
        await update.message.reply_text(f"🚫 **لا يمكن تحليل الشارت حالياً!**\nℹ️ **السبب:** {reason}")
        return

    if not OPENROUTER_API_KEY:
        await update.message.reply_text("⚠️ مفتاح OPENROUTER_API_KEY غير متصل!")
        return
    
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    exec_mode = state.get("exec_mode", "MARKET")

    await update.message.reply_text("📊 **جاري قراءة صورة الشارت المرفوعة (فريم M1 / M5) وتحليل المستويات... ⏳**")
    
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        await process_and_analyze_image(update, photo_bytes, execution_type=exec_mode)
    except Exception as e:
        await update.message.reply_text(f"⚠️ حدث خطأ أثناء معالجة الصورة: {str(e)}")

# ---------------------------------------------------------
# 11. التشغيل الرئيسي
# ---------------------------------------------------------
def main():
    keep_alive()
    t_ping = Thread(target=self_ping)
    t_ping.daemon = True
    t_ping.start()

    builder = Application.builder().token(BOT_TOKEN)
    application = builder.build()

    job_queue = application.job_queue
    job_queue.run_repeating(gold_radar_job, interval=900, first=10)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🚀 البوت يعمل بجميع الأزرار والخيارات المكتملة بدون أي تكرار...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == '__main__':
    main()
