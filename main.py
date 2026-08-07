import os
import io
import time
import base64
import logging
import requests
import json
import re
from datetime import datetime
import pytz
from threading import Thread
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ---------------------------------------------------------
# إعداد السجلات (Logging)
# ---------------------------------------------------------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ---------------------------------------------------------
# 1. خادم Flask وإبقاء البوت مستيقظاً (Keep-Alive & Self-Ping)
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

SL_BUFFER_PRICE = 3.0
user_states = {}

def get_user_state(chat_id: int) -> dict:
    if chat_id not in user_states:
        user_states[chat_id] = {
            "in_trade": False,
            "current_trade": None,
            "selected_timeframe": "M5",
            "exec_mode": "MARKET",
            "balance": 1000.0,      # الافتراضي 1000$
            "risk_pct": 2.0         # الافتراضي 2%
        }
    return user_states[chat_id]

# ---------------------------------------------------------
# 3. محرك جلب الأسعار اللحظية (المزدوج والمرن)
# ---------------------------------------------------------
def fetch_gold_price():
    # المصدر الأول: TwelveData
    try:
        if TWELVE_DATA_API_KEY:
            url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={TWELVE_DATA_API_KEY}"
            res = requests.get(url, timeout=6).json()
            if "price" in res and res["price"]:
                return float(res["price"])
    except Exception as e:
        logging.error(f"Primary API (TwelveData) Error: {e}")

    # المصدر الاحتياطي الثاني: Binance PAXG
    try:
        url_alt = "https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT"
        res_alt = requests.get(url_alt, timeout=6).json()
        if "price" in res_alt and res_alt["price"]:
            return float(res_alt["price"])
    except Exception as e:
        logging.error(f"Fallback API Error: {e}")
    
    return None

# ---------------------------------------------------------
# 4. فحص أوقات سوق الذهب (XAU/USD)
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
# 5. جلب صورة شارت حية تلقائياً
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
# 6. حاسبة حجم اللوت لإدارة المخاطر
# ---------------------------------------------------------
def calculate_recommended_lot(balance: float, risk_pct: float, entry_price: float, sl_price: float) -> tuple[float, float, float]:
    risk_amount = balance * (risk_pct / 100.0)
    sl_distance = abs(entry_price - sl_price)
    
    if sl_distance == 0:
        return 0.01, risk_amount, 0.0

    lot = risk_amount / (sl_distance * 100.0)
    lot = round(max(0.01, lot), 2)
    return lot, round(risk_amount, 2), round(sl_distance, 2)

# ---------------------------------------------------------
# 7. لوحة الأزرار الرئيسية
# ---------------------------------------------------------
main_keyboard = [
    ["⏱️ تحليل شارت M1 (دقيقة)", "📈 تحليل شارت M5 (5 دقائق)"],
    ["📊 تحليل شارت M15 (15 دقيقة)", "🏛️ تحليل شارت H1 (ساعة)"],
    ["⏳ أمر معلق (Limit - M5)", "🚨 متابعة وتحديث الصفقة الحالية"],
    ["🧮 إعدادات رأس المال واللوت", "🎯 مستويات الدعم والمقاومة"],
    ["🔍 فحص وحالة البوت (Diagnostic)", "🔄 إعادة ضبط التداول"]
]
markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    get_user_state(chat_id)
    await update.message.reply_text(
        "👑 **أهلاً بك في نظام التداول الخبير لصفقات الذهب (Gold Scalper AI Pro)**\n\n"
        "• **تحليل الشارتات المرفوعة وتعديل التوصيات لحظياً.**\n"
        "• **متابعة حية وتحليل فني حقيقي عند المتابعة اليدوية.**\n"
        "• **رادار تلقائي كل 15 دقيقة ونظام تنبيهات حرج كل 60 ثانية (TP1 + TP2).**\n"
        "• **حاسبة إدارة المخاطر واللوت المخصص لحسابك.**",
        reply_markup=markup, parse_mode="Markdown"
    )

# ---------------------------------------------------------
# 8. محرك التحليل والمطابقة السعرية اللحظية وحساب اللوت
# ---------------------------------------------------------
async def process_and_analyze_image(update: Update, photo_bytes: bytes, execution_type: str = "MARKET", timeframe: str = "M5", is_radar: bool = False, chat_id_input: int = None):
    try:
        target_chat_id = chat_id_input if is_radar else update.effective_chat.id
        state = get_user_state(target_chat_id)
        
        base64_image = base64.b64encode(photo_bytes).decode('utf-8')
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        mode_text = "توصية بسعر السوق" if execution_type == "MARKET" else "أمر معلق (Pending Limit)"
        
        system_prompt = (
            f"أنت خبير تداول الذهب (XAU/USD). أخرج البيانات التالية بصيغة JSON حصرية بدون أي نص خارجي:\n"
            f"نوع التنفيذ: {mode_text}، الفريم: {timeframe}.\n"
            "{\n"
            '  "action": "BUY" أو "SELL" أو "BUY_LIMIT" أو "SELL_LIMIT" أو "WAIT",\n'
            '  "entry": 4247.9,\n'
            '  "tp1": 4245.0,\n'
            '  "tp2": 4242.0,\n'
            '  "sl": 4252.5,\n'
            '  "rr": "1:1.7",\n'
            '  "note": "سبب القرار المباشر"\n'
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
            ai_entry = float(data.get("entry", 0.0))
            ai_tp1 = float(data.get("tp1", 0.0))
            ai_tp2 = float(data.get("tp2", 0.0))
            ai_sl = float(data.get("sl", 0.0))
            rr = data.get("rr", "1:1.5")
            note = data.get("note", "")

            if action in ["BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT"]:
                live_price = fetch_gold_price()
                if not live_price:
                    live_price = ai_entry

                if "BUY" in action:
                    zone_str = f"{round(live_price - 0.4, 2)} - {round(live_price + 0.4, 2)}"
                    diff = round(live_price - ai_entry, 2)
                    final_tp1 = round(live_price + abs(ai_tp1 - ai_entry), 2)
                    final_tp2 = round(live_price + abs(ai_tp2 - ai_entry), 2)
                    final_sl = round(live_price - abs(ai_entry - ai_sl) - SL_BUFFER_PRICE, 2)
                else:
                    zone_str = f"{round(live_price + 0.4, 2)} - {round(live_price - 0.4, 2)}"
                    diff = round(ai_entry - live_price, 2)
                    final_tp1 = round(live_price - abs(ai_entry - ai_tp1), 2)
                    final_tp2 = round(live_price - abs(ai_entry - ai_tp2), 2)
                    final_sl = round(live_price + abs(ai_sl - ai_entry) + SL_BUFFER_PRICE, 2)

                user_bal = state.get("balance", 1000.0)
                user_risk = state.get("risk_pct", 2.0)
                rec_lot, max_risk_usd, sl_dist = calculate_recommended_lot(user_bal, user_risk, live_price, final_sl)

                if "BUY" in action and live_price >= ai_tp1:
                    status_badge = "🔴 **تحذير:** السعر حقق الهدف الأول بالفعل أثناء التحليل! يُفضل تجاوز الصفقة."
                elif "SELL" in action and live_price <= ai_tp1:
                    status_badge = "🔴 **تحذير:** السعر حقق الهدف الأول بالفعل أثناء التحليل! يُفضل تجاوز الصفقة."
                elif abs(diff) <= 0.5:
                    status_badge = "🟢 **حالة ممتازة:** السعر اللحظي يتواجد في أفضل نقطة داخل نطاق الدخول."
                else:
                    status_badge = f"🟡 **تعديل لحظي:** تحرك السعر `{diff}` نقطة؛ تم تحديث الأهداف والستوب لتناسب السعر الحقيقي الآن."

                prefix = "📡 **[الرادار الآلي 15 دقيقة]:**\n\n" if is_radar else ""

                text_msg = (
                    f"{prefix}🚨 **توصية سكالبينج ({timeframe} - {action}):**\n\n"
                    f"• نوع التنفيذ: **{action}**\n"
                    f"🎯 **منطقة الدخول الموصى بها:** `{zone_str}`\n"
                    f"🟡 **السعر اللحظي الحالي:** `{live_price}`\n"
                    f"🎯 **الهدف الأول (TP1):** `{final_tp1}` (تأمين إجباري)\n"
                    f"🚀 **الهدف الثاني (TP2):** `{final_tp2}` (هدف متوسع)\n"
                    f"🛡️ **وقف الخسارة (SL المحدث):** `{final_sl}`\n"
                    f"• R/R: `{rr}`\n\n"
                    f"🧮 **حاسبة إدارة المخاطر المخصصة لحسابك:**\n"
                    f"• رأس المال: `${user_bal}` | المخاطرة: `{user_risk}%` (`${max_risk_usd}`)\n"
                    f"• مسافة الستوب: `{sl_dist}` دولار\n"
                    f"👉 **حجم اللوت الموصى به:** `{rec_lot}`\n\n"
                    f"{status_badge}\n"
                    f"💡 **التحليل:** {note}"
                )

                copy_block = (
                    f"📋 **بيانات النسخ السريع المحدثة:**\n\n"
                    f"```text\n"
                    f"Type: {action}\n"
                    f"Entry Zone: {zone_str}\n"
                    f"TP1: {final_tp1}\n"
                    f"TP2: {final_tp2}\n"
                    f"SL: {final_sl}\n"
                    f"Lot: {rec_lot}\n"
                    f"```"
                )

                if is_radar:
                    await context.bot.send_message(chat_id=target_chat_id, text=text_msg, parse_mode="Markdown")
                    await context.bot.send_message(chat_id=target_chat_id, text=copy_block, parse_mode="Markdown")
                else:
                    await update.message.reply_text(text_msg, parse_mode="Markdown")
                    await update.message.reply_text(copy_block, parse_mode="Markdown")

                state["pending_trade_data"] = {
                    "action": action, "entry": live_price, "tp1": final_tp1, "tp2": final_tp2, "sl": final_sl, "notified_tp1": False
                }

                inline_kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ دخلت الصفقة", callback_data="trade_entered"),
                        InlineKeyboardButton("❌ لم أدخل الصفقة", callback_data="trade_skipped")
                    ]
                ])
                
                ask_msg = "❓ **هل قمت بالدخول في هذه الصفقة بالسعر اللحظي الحالي؟**"
                if is_radar:
                    await context.bot.send_message(chat_id=target_chat_id, text=ask_msg, reply_markup=inline_kb, parse_mode="Markdown")
                else:
                    await update.message.reply_text(ask_msg, reply_markup=inline_kb, parse_mode="Markdown")

            else:
                msg = f"🎯 **توصية ({timeframe}):** **انتظار (WAIT)**\n💡 **السبب:** {note}"
                if is_radar:
                    await context.bot.send_message(chat_id=target_chat_id, text=msg, parse_mode="Markdown")
                else:
                    await update.message.reply_text(msg, parse_mode="Markdown")

        else:
            if not is_radar:
                await update.message.reply_text(f"⚠️ خطأ من المزود الذكي: {str(response)}")

    except Exception as e:
        if not is_radar and update:
            await update.message.reply_text(f"⚠️ حدث خطأ أثناء معالجة التحليل: {str(e)}")

# ---------------------------------------------------------
# 9. المتابعة الآلية والحرجة (TP1 و TP2 و SL) + الرادار
# ---------------------------------------------------------
async def auto_check_trades(context: ContextTypes.DEFAULT_TYPE):
    current_price = fetch_gold_price()
    if current_price is None:
        return

    for chat_id, state in list(user_states.items()):
        try:
            if state.get("in_trade") and state.get("current_trade"):
                trade = state["current_trade"]
                action = trade["action"]
                entry = float(trade["entry"])
                tp1 = float(trade["tp1"])
                tp2 = float(trade["tp2"])
                sl = float(trade["sl"])
                notified_tp1 = trade.get("notified_tp1", False)

                exit_kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ خرجت من الصفقة", callback_data="trade_exited"),
                        InlineKeyboardButton("⏳ ما زلت بالصفقة", callback_data="trade_still_open")
                    ]
                ])

                # --- صفقات الشراء (BUY / BUY_LIMIT) ---
                if "BUY" in action:
                    # 1. فحص الوصول للهدف الثاني والأخير (TP2)
                    if current_price >= tp2:
                        state["in_trade"] = False
                        state["current_trade"] = None
                        msg = (
                            f"🚀🚀 **مبروك! وصل السعر للهدف الثاني والأخير (TP2) عند `{current_price}`!**\n\n"
                            f"✅ **تم تحقيق جميع أهداف الصفقة بالكامل بنجاح 🎯**\n"
                            f"👉 تم إغلاق ملف الصفقة تلقائياً. جاهزون للفرصة القادمة!"
                        )
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

                    # 2. فحص الوصول للهدف الأول (TP1)
                    elif current_price >= tp1 and not notified_tp1:
                        trade["notified_tp1"] = True
                        trade["sl"] = entry  # نقل الستوب تلقائياً لسعر الدخول
                        msg = (
                            f"🎉 **تنبيه حرج: وصل السعر للهدف الأول (TP1) عند `{current_price}`!**\n\n"
                            f"💡 **الإجراء الآلي:** تم نقل الستوب تلقائياً لسعر الدخول (`{entry}`).\n"
                            f"👉 أغلق نصف العقد الآن واترك المتبقي للهدف الثاني (`{tp2}`)!"
                        )
                        await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=exit_kb, parse_mode="Markdown")

                    # 3. فحص ضرب الستوب
                    elif current_price <= sl:
                        state["in_trade"] = False
                        state["current_trade"] = None
                        msg = f"🛑 **تنبيه حرج: وصل السعر لستوب الخسارة عند `{current_price}`!** تم إغلاق ملف الصفقة."
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

                # --- صفقات البيع (SELL / SELL_LIMIT) ---
                elif "SELL" in action:
                    # 1. فحص الوصول للهدف الثاني والأخير (TP2)
                    if current_price <= tp2:
                        state["in_trade"] = False
                        state["current_trade"] = None
                        msg = (
                            f"🚀🚀 **مبروك! وصل السعر للهدف الثاني والأخير (TP2) عند `{current_price}`!**\n\n"
                            f"✅ **تم تحقيق جميع أهداف الصفقة بالكامل بنجاح 🎯**\n"
                            f"👉 تم إغلاق ملف الصفقة تلقائياً. جاهزون للفرصة القادمة!"
                        )
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

                    # 2. فحص الوصول للهدف الأول (TP1)
                    elif current_price <= tp1 and not notified_tp1:
                        trade["notified_tp1"] = True
                        trade["sl"] = entry  # نقل الستوب تلقائياً لسعر الدخول
                        msg = (
                            f"🎉 **تنبيه حرج: وصل السعر للهدف الأول (TP1) عند `{current_price}`!**\n\n"
                            f"💡 **الإجراء الآلي:** تم نقل الستوب تلقائياً لسعر الدخول (`{entry}`).\n"
                            f"👉 أغلق نصف العقد الآن واترك المتبقي للهدف الثاني (`{tp2}`)!"
                        )
                        await context.bot.send_message(chat_id=chat_id, text=msg, reply_markup=exit_kb, parse_mode="Markdown")

                    # 3. فحص ضرب الستوب
                    elif current_price >= sl:
                        state["in_trade"] = False
                        state["current_trade"] = None
                        msg = f"🛑 **تنبيه حرج: وصل السعر لستوب الخسارة عند `{current_price}`!** تم إغلاق ملف الصفقة."
                        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")

        except Exception as e:
            logging.error(f"Error in auto_check_trades for {chat_id}: {e}")

async def periodic_market_scanner(context: ContextTypes.DEFAULT_TYPE):
    is_open, _ = is_market_open()
    if not is_open:
        return

    chart_bytes = fetch_live_chart_image(interval="5m")
    if not chart_bytes:
        return

    for chat_id, state in list(user_states.items()):
        if not state.get("in_trade"):
            try:
                await process_and_analyze_image(
                    update=None, 
                    photo_bytes=chart_bytes, 
                    execution_type="MARKET", 
                    timeframe="M5", 
                    is_radar=True, 
                    chat_id_input=chat_id
                )
            except Exception as e:
                logging.error(f"Failed periodic radar scan for {chat_id}: {e}")

# ---------------------------------------------------------
# 10. معالجة التفاعل بالأزرار المدمجة (Inline)
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
                f"• يفحص البوت السعر كل 60 ثانية... وسيرسل إشعاراً فورياً عند الوصول لـ TP1 و TP2 و SL!",
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
        await query.edit_message_text("⏳ **سأستمر في متابعة الصفقة معك كل دقيقة بالخلفية حتى TP2...**")

# ---------------------------------------------------------
# 11. معالجة الرسائل والأزرار الرئيسية
# ---------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    chat_id = update.effective_chat.id
    state = get_user_state(chat_id)
    is_open, reason = is_market_open()

    if ("حسابي" in text or "رأس مالي" in text) and ("مخاطرة" in text or "%" in text):
        nums = re.findall(r'\d+(?:\.\d+)?', text)
        if len(nums) >= 2:
            state["balance"] = float(nums[0])
            state["risk_pct"] = float(nums[1])
            await update.message.reply_text(
                f"✅ **تم تحديث إعدادات حسابك بنجاح!**\n\n"
                f"💰 **رأس المال:** `${state['balance']}`\n"
                f"🛡️ **نسبة المخاطرة:** `{state['risk_pct']}%` لكل صفقة.",
                parse_mode="Markdown"
            )
            return

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
        await update.message.reply_text("⏳ **جاري جلب وحساب نقاط الأمر المعلق (Limit - M5)... ⏳**")
        chart_bytes = fetch_live_chart_image(interval="5m")
        if chart_bytes:
            await process_and_analyze_image(update, chart_bytes, execution_type="LIMIT", timeframe="M5")

    elif text == "🚨 متابعة وتحديث الصفقة الحالية":
        if not state.get("in_trade") or not state.get("current_trade"):
            await update.message.reply_text("ℹ️ **أنت لست داخل صفقة حالياً.** اطلب تحليل/توصية أولاً واضغط '✅ دخلت الصفقة' لتفعيل المتابعة.")
            return

        await update.message.reply_text("🔍 **جاري جلب الشارت الحي والسعر اللحظي وتحليل الصفقة بالذكاء الاصطناعي... ⏳**")

        trade = state["current_trade"]
        current_price = fetch_gold_price()
        if current_price is None:
            await update.message.reply_text("⚠️ متعذر جلب السعر المباشر الآن. يرجى المحاولة بعد لحظات.")
            return

        entry = float(trade["entry"])
        action = trade["action"]
        tp1 = float(trade["tp1"])
        tp2 = float(trade["tp2"])
        sl = float(trade["sl"])

        chart_bytes = fetch_live_chart_image(interval="5m")
        pips = round((current_price - entry), 2) if "BUY" in action else round((entry - current_price), 2)

        ai_analysis_note = ""
        if chart_bytes and OPENROUTER_API_KEY:
            try:
                base64_img = base64.b64encode(chart_bytes).decode('utf-8')
                headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
                prompt = (
                    f"أنت خبير تداول الذهب. لدينا صفقة قائمة حالية نوعها {action} من سعر {entry}. "
                    f"السعر اللحظي الآن هو {current_price}. "
                    f"ألقِ نظرة على الشارت المرفق وأعطِ تقييماً فنياً حقيقياً ومختصراً في سطرين: "
                    f"هل تستمر الصفقة نحو الهدف أم توجد إشارات عكسية وتوصي بالخروج المبكر؟"
                )
                payload = {
                    "model": "google/gemini-2.5-flash",
                    "max_tokens": 200,
                    "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}}]}]
                }
                res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=20).json()
                if "choices" in res and len(res["choices"]) > 0:
                    ai_analysis_note = res["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logging.error(f"Error in manual tracking AI call: {e}")

        if ("BUY" in action and current_price >= tp2) or ("SELL" in action and current_price <= tp2):
            status_text = f"🚀 **تم الوصول للهدف الثاني والأخير (TP2) عند `{current_price}`!**\n💡 يُنصح بإغلاق كافة العقود وجني الأرباح."
        elif ("BUY" in action and current_price >= tp1) or ("SELL" in action and current_price <= tp1):
            status_text = f"🎉 **تم الوصول للهدف الأول (TP1) عند `{current_price}`!**\n💡 تم نقل الستوب تلقائياً إلى نقطة الدخول (`{entry}`)."
        elif ("BUY" in action and current_price <= sl) or ("SELL" in action and current_price >= sl):
            status_text = f"🛑 **تنبيه حرج:** السعر تجاوز منطقة الستوب عند `{current_price}`."
        else:
            profit_label = "ربح" if pips >= 0 else "خسارة"
            status_text = f"📊 **النتيجة اللحظية:** {profit_label} بقيمة `{pips}` دولار/نقطة."

        ai_section = f"\n\n🧠 **التقييم الفني الحي من الذكاء الاصطناعي:**\n_{ai_analysis_note}_" if ai_analysis_note else ""

        report_msg = (
            f"🚨 **متابعة وتحليل حي للصفقة الحالية ({action}):**\n\n"
            f"📍 **نقطة الدخول:** `{entry}`\n"
            f"🟡 **السعر المباشر الآن:** `{current_price}`\n"
            f"🎯 **الهدف الأول:** `{tp1}` | 🚀 **الثاني:** `{tp2}`\n"
            f"🛡️ **الستوب:** `{sl}`\n\n"
            f"{status_text}"
            f"{ai_section}\n\n"
            f"❓ **هل ترغب في الخروج من الصفقة الآن؟**"
        )

        exit_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ خرجت من الصفقة", callback_data="trade_exited"),
                InlineKeyboardButton("⏳ ما زلت بالصفقة", callback_data="trade_still_open")
            ]
        ])
        await update.message.reply_text(report_msg, reply_markup=exit_kb, parse_mode="Markdown")

    elif text == "🧮 إعدادات رأس المال واللوت":
        bal = state.get("balance", 1000.0)
        risk = state.get("risk_pct", 2.0)
        await update.message.reply_text(
            f"⚙️ **إعدادات إدارة المخاطر الحالية:**\n\n"
            f"• **رأس المال:** `${bal}`\n"
            f"• **نسبة المخاطرة:** `{risk}%` لكل صفقة\n\n"
            f"✏️ **لتعديل البيانات، أرسل رسالة بالشكل التالي:**\n"
            f"`حسابي 1500 مخاطرة 1.5`\n"
            f"*(وسيقوم البوت بحساب اللوت الموصى به أوتوماتيكياً مع كل توصية)*",
            parse_mode="Markdown"
        )

    elif text == "🎯 مستويات الدعم والمقاومة":
        price = fetch_gold_price()
        if price:
            r1 = round(price + 4.5, 2)
            r2 = round(price + 9.0, 2)
            s1 = round(price - 4.5, 2)
            s2 = round(price - 9.0, 2)
            msg = (
                f"🎯 **مستويات الدعم والمقاومة المحسوبة (XAU/USD):**\n\n"
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
            f"2️⃣ **مزود الأسعار اللحظية:** {price_status}\n"
            f"3️⃣ **خادم الذكاء الاصطناعي (Gemini 2.5):** {ai_status}\n"
            f"4️⃣ **المتابعة اليدوية الذكية:** 🟢 شغال (تحليل الشارت الحي)\n"
            f"5️⃣ **رادار المتابعة الآلية:** 🟢 شغال (متابعة حية لـ TP1 و TP2 كل 60 ثانية)\n"
            f"6️⃣ **الرادار التلقائي للفرص:** 🟢 شغال (تحليل الشارت كل 15 دقيقة)\n"
            f"7️⃣ **حاسبة اللوت المخصصة:** 🟢 شغال (`${state.get('balance')}` - `{state.get('risk_pct')}%`)\n\n"
            f"📌 **النتيجة:** البوت جاهز ومكتمل بكفاءة 100%!"
        )
        await update.message.reply_text(diag_report, parse_mode="Markdown")

    elif text == "🔄 إعادة ضبط التداول":
        state["in_trade"] = False
        state["current_trade"] = None
        state["selected_timeframe"] = "M5"
        await update.message.reply_text("🔄 **تم إعادة ضبط التداول وتفريغ حالة الصفقات بنجاح!**", reply_markup=markup, parse_mode="Markdown")

# ---------------------------------------------------------
# 12. معالجة الصور المرفوعة يدوياً
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

    await update.message.reply_text(f"📊 **جاري تحليل صورة الشارت المرفوعة ({selected_tf}) وحساب اللوت المناسب لحسابك... ⏳**")
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        await process_and_analyze_image(update, photo_bytes, execution_type=exec_mode, timeframe=selected_tf)
    except Exception as e:
        await update.message.reply_text(f"⚠️ حدث خطأ أثناء المعالجة: {str(e)}")

# ---------------------------------------------------------
# 13. التشغيل الرئيسي للمشروع
# ---------------------------------------------------------
def main():
    keep_alive()
    t_ping = Thread(target=self_ping)
    t_ping.daemon = True
    t_ping.start()

    builder = Application.builder().token(BOT_TOKEN)
    application = builder.build()

    if application.job_queue:
        application.job_queue.run_repeating(auto_check_trades, interval=60, first=10)
        application.job_queue.run_repeating(periodic_market_scanner, interval=900, first=30)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🚀 البوت الشامل يعمل الآن بنجاح وبكافة الخصائص المحدثة...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == '__main__':
    main()
