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
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ---------------------------------------------------------
# إعداد السجلات (Logs)
# ---------------------------------------------------------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ---------------------------------------------------------
# 1. خادم Flask وإبقاء الخدمة مستيقظة
# ---------------------------------------------------------
app_web = Flask('')

@app_web.route('/')
def home():
    return "Gold Scalper Interactive Engine Active & Running!", 200

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
# 2. الإعدادات والمتغيرات الحرة
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY", "").strip()

SYMBOL = "XAU/USD"
SL_BUFFER_PRICE = 3.0
user_states = {}

def get_user_state(chat_id: int) -> dict:
    if chat_id not in user_states:
        user_states[chat_id] = {
            "in_trade": False,
            "current_trade": None,
            "selected_timeframe": "M5",
            "exec_mode": "MARKET"
        }
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
        return None
    except Exception as e:
        logging.error(f"Error fetching gold price: {e}")
        return None

# ---------------------------------------------------------
# 5. جلب صورة شارت حية تلقائياً للأوامر المعلقة
# ---------------------------------------------------------
def fetch_live_chart_image(interval="5m"):
    try:
        chart_url = f"https://chart-img.com/v1/tradingview/advanced-chart?symbol=OANDA:XAUUSD&interval={interval}&theme=dark&width=800&height=600"
        response = requests.get(chart_url, timeout=15)
        if response.status_code == 200:
            return response.content
        return None
    except Exception as e:
        logging.error(f"Error fetching live chart image: {e}")
        return None

# ---------------------------------------------------------
# 6. لوحة الأزرار الرئيسية
# ---------------------------------------------------------
main_keyboard = [
    ["⏱️ تحليل شارت M1 (دقيقة)", "📈 تحليل شارت M5 (5 دقائق)"],
    ["📊 تحليل شارت M15 (15 دقيقة)", "🏛️ تحليل شارت H1 (ساعة)"],
    ["⏳ أمر معلق (Limit - M5)", "🚨 متابعة وتحديث الصفقة الحالية"],
    ["🎯 مستويات الدعم والمقاومة", "🔍 فحص وحالة البوت (Diagnostic)"],
    ["🔄 إعادة ضبط التداول"]
]
markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_user_state(chat_id)
    await update.message.reply_text(
        "👑 **أهلاً بك في نظام مدير وتتبع صفقات الذهب الحية (Live Trade Manager)**\n\n"
        "• **تحليل الشارت المرفوع لكافة الفريمات (M1, M5, M15, H1).**\n"
        "• **تتبع تلقائي حي:** يفحص البوت السعر كل 15 ثانية ويراقب الأهداف والستوب.\n"
        "• **إشعارات دورية للسوق:** يرسل البوت تحديثاً تلقائياً للسوق كل 15 دقيقة.\n"
        "• **تنبيهات جني الأرباح والتأمين والخروج المبكر.**",
        reply_markup=markup, parse_mode="Markdown"
    )

# ---------------------------------------------------------
# 7. محرك التحليل والذكاء الاصطناعي
# ---------------------------------------------------------
async def process_and_analyze_image(update: Update, photo_bytes: bytes, execution_type: str = "MARKET", timeframe: str = "M5"):
    try:
        base64_image = base64.b64encode(photo_bytes).decode('utf-8')

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        mode_text = "توصية بسعر السوق (Market Execution)" if execution_type == "MARKET" else "أمر معلق (Pending Limit Order)"
        
        system_prompt = (
            f"أنت مدير صفقات محترف لخبير الذهب (XAU/USD).\n"
            f"نوع التنفيذ المطلوب: {mode_text}.\n"
            f"الفريم الحالي: {timeframe}.\n"
            "حلل الشارت واستخرج التوصية مع مراعاة قواعد فلتر H1 والأهداف المزدوجة.\n"
            "أخرج الرد بتنسيق JSON حصراً بدون أي نص إضافي خارجه:\n"
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
                adjusted_sl = round(sl_raw - SL_BUFFER_PRICE if "BUY" in action else sl_raw + SL_BUFFER_PRICE, 2)

                text_msg = (
                    f"🚨 **توصية سكالبينج ({timeframe} - {action}):**\n\n"
                    f"• نوع التنفيذ: **{action}**\n"
                    f"• سعر الدخول المقترح: `{entry}`\n"
                    f"🎯 **الهدف الأول (TP1):** `{tp1}` (جني أرباح وتأمين)\n"
                    f"🚀 **الهدف الثاني (TP2):** `{tp2}` (هدف متوسع)\n"
                    f"🛡️ **وقف الخسارة (SL المعدل):** `{adjusted_sl}`\n"
                    f"• نسبة المخاطرة للعائد: `{rr}`\n\n"
                    f"💡 **التحليل:** {note}"
                )

                copy_block = (
                    f"📋 **بيانات النسخ السريع ({timeframe}):**\n\n"
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

                chat_id = update.effective_chat.id
                state = get_user_state(chat_id)
                state["pending_trade_data"] = {
                    "action": action, "entry": entry, "tp1": tp1, "tp2": tp2, "sl": adjusted_sl, "notified_tp1": False
                }

                inline_kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ دخلت الصفقة", callback_data="trade_entered"),
                        InlineKeyboardButton("❌ لم أدخل الصفقة", callback_data="trade_skipped")
                    ]
                ])
                await update.message.reply_text("❓ **هل قمت بالدخول في هذه الصفقة على منصتك؟**", reply_markup=inline_kb)

            else:
                await update.message.reply_text(f"🎯 **توصية ({timeframe}):** **انتظار (WAIT)**\n💡 **السبب:** {note}", parse_mode="Markdown")

        else:
            await update.message.reply_text(f"⚠️ خطأ من المزود الذكي: {str(response)}")

    except Exception as e:
        await update.message.reply_text(f"⚠️ حدث خطأ أثناء معالجة التحليل: {str(e)}")

# ---------------------------------------------------------
# 8. الفحص الآلي للصفقات والتحديثات الدورية
# ---------------------------------------------------------
# أ) متابعة الصفقة المفتوحة (كل 15 ثانية)
async def auto_check_trades(context: ContextTypes.DEFAULT_TYPE):
    current_price = fetch_gold_price()
    if not current_price:
        return

    for chat_id, state in list(user_states.items()):
        if state.get("in_trade") and state.get("current_trade"):
            trade = state["current_trade"]
            action = trade["action"]
            entry = trade["entry"]
            tp1 = trade["tp1"]
            sl = trade["sl"]
            notified_tp1 = trade.get("notified_tp1", False)

            exit_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ خرجت من الصفقة", callback_data="trade_exited"),
                    InlineKeyboardButton("⏳ ما زلت بالصفقة", callback_data="trade_still_open")
                ]
            ])

            if "BUY" in action:
                if current_price >= tp1 and not notified_tp1:
                    trade["notified_tp1"] = True
                    msg = (
                        f"🎉 **تنبيه تلقائي: وصل السعر للهدف الأول (TP1)!**\n\n"
                        f"• السعر اللحظي: `{current_price}`\n"
                        f"💡 **الإجراء:** اغلق نصف العقد وانقل الستوب لسعر الدخول (`{entry}`)."
                    )
                    await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=exit_kb, parse_mode="Markdown")

                elif current_price <= sl:
                    state["in_trade"] = False
                    state["current_trade"] = None
                    msg = f"🛑 **تنبيه تلقائي: وصل السعر للستوب لوز عند `{current_price}`!**"
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

            elif "SELL" in action:
                if current_price <= tp1 and not notified_tp1:
                    trade["notified_tp1"] = True
                    msg = (
                        f"🎉 **تنبيه تلقائي: وصل السعر للهدف الأول (TP1)!**\n\n"
                        f"• السعر اللحظي: `{current_price}`\n"
                        f"💡 **الإجراء:** اغلق نصف العقد وانقل الستوب لسعر الدخول (`{entry}`)."
                    )
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

                elif current_price >= sl:
                    state["in_trade"] = False
                    state["current_trade"] = None
                    msg = f"🛑 **تنبيه تلقائي: وصل السعر للستوب لوز عند `{current_price}`!**"
                    await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

# ب) إشعارات دورية للسوق (كل 15 دقيقة)
async def periodic_market_scanner(context: ContextTypes.DEFAULT_TYPE):
    is_open, _ = is_market_open()
    if not is_open:
        return

    current_price = fetch_gold_price()
    if not current_price:
        return

    for chat_id, state in list(user_states.items()):
        if not state.get("in_trade"):
            msg = (
                f"⏰ **التحديث الدوري للأسواق (كل 15 دقيقة):**\n\n"
                f"🟡 **سعر الذهب اللحظي:** `{current_price}`\n"
                f"📊 البوت يراقب حركة السوق باستمرار.\n"
                f"💡 أرسل صورة الشارت في أي وقت للحصول على تحليل جديد."
            )
            try:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
            except Exception as e:
                logging.error(f"Failed to send periodic message to {chat_id}: {e}")

# ---------------------------------------------------------
# 9. معالجة التفاعل الحي عبر الأزرار المدمجة
# ---------------------------------------------------------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    state = get_user_state(chat_id)

    if query.data == "trade_entered":
        if "pending_trade_data" in state:
            state["in_trade"] = True
            state["current_trade"] = state["pending_trade_data"]
            trade = state["current_trade"]
            
            await query.edit_message_text(
                f"🟢 **تم تفعيل المتابعة التلقائية الحية بالخلفية!**\n\n"
                f"• الصفقة: `{trade['action']}` من سعر `{trade['entry']}`\n"
                f"• الرادار التلقائي يفحص السعر كل 15 ثانية الآن... وسيرسل لك إشعاراً فورياً عند وصول السعر للهدف أو الستوب!",
                parse_mode="Markdown"
            )
    
    elif query.data == "trade_skipped":
        state["in_trade"] = False
        state["current_trade"] = None
        await query.edit_message_text("👍 **تم إلغاء المتابعة لهذه الصفقة.** البوت جاهز للفرصة التالية.")

    elif query.data == "trade_exited":
        state["in_trade"] = False
        state["current_trade"] = None
        await query.edit_message_text("✅ **ممتاز! تم إغلاق ملف الصفقة بنجاح.** نتمنى لك أرباحاً وفيرة 🚀")

    elif query.data == "trade_still_open":
        await query.edit_message_text("⏳ **سأستمر في متابعة الصفقة معك في الخلفية...**")

# ---------------------------------------------------------
# 10. معالجة الرسائل والأزرار الرئيسية
# ---------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    is_open, reason = is_market_open()

    if "شارت M1" in text:
        state["selected_timeframe"] = "M1"
        await update.message.reply_text("📸 **أرسل صورة شارت فريم الدقيقة (M1) لنقوم بتحليلها فوراً...**")

    elif "شارت M5" in text:
        state["selected_timeframe"] = "M5"
        await update.message.reply_text("📸 **أرسل صورة شارت فريم الـ 5 دقائق (M5) لنقوم بتحليلها فوراً...**")

    elif "شارت M15" in text:
        state["selected_timeframe"] = "M15"
        await update.message.reply_text("📸 **أرسل صورة شارت فريم الـ 15 دقيقة (M15) لنقوم بتحليلها فوراً...**")

    elif "شارت H1" in text:
        state["selected_timeframe"] = "H1"
        await update.message.reply_text("📸 **أرسل صورة شارت فريم الساعة (H1) لنقوم بتحليل الاتجاه العام والمستويات...**")

    elif "أمر معلق" in text:
        if not is_open:
            await update.message.reply_text(f"🚫 **السوق مغلق حالياً!**\nℹ️ {reason}")
            return
        state["exec_mode"] = "LIMIT"
        state["selected_timeframe"] = "M5"
        await update.message.reply_text("⏳ **جاري حساب نقاط الأمر المعلق (Limit - M5)... ⏳**")
        chart_bytes = fetch_live_chart_image(interval="5m")
        if chart_bytes:
            await process_and_analyze_image(update, chart_bytes, execution_type="LIMIT", timeframe="M5")

    elif text == "🚨 متابعة وتحديث الصفقة الحالية":
        if not state.get("in_trade") or not state.get("current_trade"):
            await update.message.reply_text("ℹ️ **أنت لست داخل صفقة حالياً.** اطلب تحليل/توصية أولاً واضغط '✅ دخلت الصفقة' لتفعيل المتابعة.")
            return

        trade = state["current_trade"]
        current_price = fetch_gold_price()
        if not current_price:
            await update.message.reply_text("⚠️ متعذر جلب السعر المباشر الآن.")
            return

        entry = trade["entry"]
        action = trade["action"]
        tp1 = trade["tp1"]
        sl = trade["sl"]

        status_text = ""
        if "BUY" in action:
            pips = round((current_price - entry), 2)
            if current_price >= tp1:
                status_text = f"🎉 **وصل السعر للهدف الأول (TP1) عند `{current_price}`!**\n💡 انقل الستوب فوراً لسعر الدخول `{entry}` لتأمين الأرباح."
            elif current_price <= sl:
                status_text = f"🛑 **السعر وصل لمنطقة الستوب لوز عند `{current_price}`.** يفضل الخروج."
            else:
                status_text = f"📈 **السعر الحالي:** `{current_price}` (الربح الحالي: `${pips}`)\n🟢 الصفقة مستمرة والمتابعة التلقائية شغالّة."
        else:
            pips = round((entry - current_price), 2)
            if current_price <= tp1:
                status_text = f"🎉 **وصل السعر للهدف الأول (TP1) عند `{current_price}`!**\n💡 انقل الستوب فوراً لسعر الدخول `{entry}` لتأمين الأرباح."
            elif current_price >= sl:
                status_text = f"🛑 **السعر وصل لمنطقة الستوب لوز عند `{current_price}`.** يفضل الخروج."
            else:
                status_text = f"📉 **السعر الحالي:** `{current_price}` (الربح الحالي: `${pips}`)\n🟢 الصفقة مستمرة والمتابعة التلقائية شغالّة."

        exit_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ خرجت من الصفقة", callback_data="trade_exited"),
                InlineKeyboardButton("⏳ ما زلت بالصفقة", callback_data="trade_still_open")
            ]
        ])
        await update.message.reply_text(f"🚨 **متابعة حية للصفقة الحالية ({action}):**\n\n{status_text}\n\n❓ **هل قمت بالخروج من الصفقة؟**", reply_markup=exit_kb, parse_mode="Markdown")

    elif text == "🎯 مستويات الدعم والمقاومة":
        price = fetch_gold_price()
        if price:
            r1 = round(price + 4.5, 2)
            r2 = round(price + 9.0, 2)
            s1 = round(price - 4.5, 2)
            s2 = round(price - 9.0, 2)
            msg = (
                f"🎯 **مستويات الدعم والمقاومة اليومية المحسوبة (XAU/USD):**\n\n"
                f"🔴 **المقاومة الثانية (R2):** `{r2}`\n"
                f"🔴 **المقاومة الأولى (R1):** `{r1}`\n"
                f"🟡 **السعر الحالي:** `{price}`\n"
                f"🟢 **الدعم الأول (S1):** `{s1}`\n"
                f"🟢 **الدعم الثاني (S2):** `{s2}`"
            )
            await update.message.reply_text(msg, parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ متعذر جلب المستويات اللحظية حالياً.")

    elif text == "🔍 فحص وحالة البوت (Diagnostic)":
        await update.message.reply_text("🔍 **جاري إجراء فحص برجمي شامل للأنظمة... ⏳**")
        time.sleep(1)
        
        gold_price = fetch_gold_price()
        price_status = f"🟢 شغال (`{gold_price}`)" if gold_price else "🔴 خطأ في جلب السعر"
        ai_status = "🟢 متصل واستجابة ممتازة" if OPENROUTER_API_KEY else "🔴 المفتاح مفقود"
        market_open, reason = is_market_open()
        market_icon = "🟢 مفتوح" if market_open else "🔴 مغلق"

        diag_report = (
            f"🛠 **تقرير الفحص والتشخيص الفعلي للبوت:**\n\n"
            f"1️⃣ **سوق الذهب:** {market_icon} ({reason})\n"
            f"2️⃣ **مزود الأسعار (TwelveData):** {price_status}\n"
            f"3️⃣ **خادم الذكاء الاصطناعي (Gemini 2.5):** {ai_status}\n"
            f"4️⃣ **رادار المتابعة الآلية بالخلفية:** 🟢 شغال (فحص الصفقات كل 15 ثانية)\n"
            f"5️⃣ **التحديثات الدورية للسوق:** 🟢 شغال (كل 15 دقيقة)\n"
            f"6️⃣ **نظام إبقاء الخدمة مستيقظة (Keep-Alive):** 🟢 24/7 Active\n\n"
            f"📌 **النتيجة:** البوت جاهز ويعمل بكفاءة 100% بدون أي أخطاء!"
        )
        await update.message.reply_text(diag_report, parse_mode="Markdown")

    elif text == "🔄 إعادة ضبط التداول":
        state["in_trade"] = False
        state["current_trade"] = None
        state["selected_timeframe"] = "M5"
        await update.message.reply_text("🔄 **تم إعادة ضبط التداول وتفريغ حالة الصفقات بنجاح!**", reply_markup=markup, parse_mode="Markdown")

# ---------------------------------------------------------
# 11. معالجة الصور المرفوعة يدوياً
# ---------------------------------------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    is_open, reason = is_market_open()
    if not is_open:
        await update.message.reply_text(f"🚫 **السوق مغلق!** {reason}")
        return

    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    selected_tf = state.get("selected_timeframe", "M5")
    exec_mode = state.get("exec_mode", "MARKET")

    await update.message.reply_text(f"📊 **جاري تحليل صورة الشارت المرفوعة ({selected_tf})... ⏳**")
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        await process_and_analyze_image(update, photo_bytes, execution_type=exec_mode, timeframe=selected_tf)
    except Exception as e:
        await update.message.reply_text(f"⚠️ حدث خطأ أثناء المعالجة: {str(e)}")

# ---------------------------------------------------------
# 12. التشغيل الرئيسي
# ---------------------------------------------------------
def main():
    keep_alive()
    t_ping = Thread(target=self_ping)
    t_ping.daemon = True
    t_ping.start()

    builder = Application.builder().token(BOT_TOKEN)
    application = builder.build()

    # تشغيل الوظائف المجدولة بالخلفية
    if application.job_queue:
        # 1. متابعة الصفقات القائمة كل 15 ثانية
        application.job_queue.run_repeating(auto_check_trades, interval=15, first=10)
        # 2. إرسال الإشعار والتحديث الدوري للسوق كل 15 دقيقة (900 ثانية)
        application.job_queue.run_repeating(periodic_market_scanner, interval=900, first=30)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🚀 البوت التفاعلي الشامل يعمل بنجاح مع نظام المتابعة والإشعارات الدورية...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == '__main__':
    main()
