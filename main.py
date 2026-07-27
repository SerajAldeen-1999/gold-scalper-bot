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
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# محاولة استيراد مكتبة MetaTrader 5 (تتطلب نظام Windows مثبت عليه MT5)
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

# ---------------------------------------------------------
# إعداد السجلات (Logs)
# ---------------------------------------------------------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# ---------------------------------------------------------
# 1. خادم Flask لإبقاء الخدمة مستيقظة
# ---------------------------------------------------------
app_web = Flask('')

@app_web.route('/')
def home():
    return "Gold Scalper Pro MT5 Auto-Execution Engine Active!", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app_web.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ---------------------------------------------------------
# 2. الإعدادات وبيانات الحساب الديمو المباشرة
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

# 🔒 بيانات حساب JustMarket الديمو المباشرة الخاصة بك:
MT5_LOGIN = 1200247173
MT5_PASSWORD = "111213_Seraj"
MT5_SERVER = "JustMarket-Demo3"

SYMBOL = "XAUUSD"
LOT_SIZE = 0.01          # حجم اللوت الافتراضي
SL_BUFFER_PRICE = 1.5    # هامش الأمان الإضافي للستوب لوز (1.5 دولار لحماية الصفقة)

# ---------------------------------------------------------
# 3. الاتصال بحساب MetaTrader 5
# ---------------------------------------------------------
def init_mt5_connection():
    if not MT5_AVAILABLE:
        logging.warning("مكتبة MetaTrader5 غير مثبتة أو النظام ليس Windows.")
        return False
    
    if not mt5.initialize():
        logging.error(f"فشل تهيئة MT5: {mt5.last_error()}")
        return False

    authorized = mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if authorized:
        logging.info("✅ تم الاتصال بحساب MetaTrader 5 بنجاح!")
        return True
    else:
        logging.error(f"❌ فشل تسجيل الدخول لـ MT5: {mt5.last_error()}")
        return False

# ---------------------------------------------------------
# 4. دالة تنفيذ الصفقة الفعلية على MT5
# ---------------------------------------------------------
def execute_mt5_order(action_type: str, sl_price: float, tp_price: float):
    if not MT5_AVAILABLE or not mt5.terminal_info():
        if not init_mt5_connection():
            return False, "غير قادر على الاتصال بمنصة MetaTrader 5 (تأكد أن البرنامج شغال على جهاز Windows)."

    symbol_info = mt5.symbol_select(SYMBOL, True)
    if not symbol_info:
        return False, f"الرمز {SYMBOL} غير متاح في المنصة."

    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        return False, "تعذر جلب سعر السوق اللحظي من MT5."

    order_type = mt5.ORDER_TYPE_BUY if action_type == "BUY" else mt5.ORDER_TYPE_SELL
    price = tick.ask if action_type == "BUY" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT_SIZE,
        "type": order_type,
        "price": price,
        "sl": float(sl_price),
        "tp": float(tp_price),
        "deviation": 20,
        "magic": 100200,
        "comment": "Gold Scalper Telegram AI",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return False, f"فشل تنفيذ الأمر: {result.comment} (كود: {result.retcode})"
    
    return True, f"تم فتح صفقة {action_type} بنجاح عند السعر {result.price}!"

# ---------------------------------------------------------
# 5. معالجة الصور والتوصيات والأزرار التفاعلية
# ---------------------------------------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not OPENROUTER_API_KEY:
        await update.message.reply_text("⚠️ مفتاح OPENROUTER_API_KEY غير متصل!")
        return
    
    await update.message.reply_text("⚡️ جاري تحليل الشارت واستخراج التوصية مع حساب الستوب المعدل... ⏳")
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        base64_image = base64.b64encode(photo_bytes).decode('utf-8')

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        system_prompt = (
            "أنت خبير تداول سكالبينج محترف للذهب (XAU/USD).\n"
            "حلل الشارت المرفق واستخرج التوصية مباشرة بتنسيق JSON حصراً وبدون أي مقدمات أو نصوص خارج الـ JSON.\n\n"
            "ملاحظة الستوب لوز (SL): احسب SL بدقة أسفل/أعلى الهيكل.\n\n"
            "صيغة الـ JSON المطلوبة تماماً:\n"
            "{\n"
            '  "action": "BUY" أو "SELL" أو "WAIT",\n'
            '  "entry": 4075.50,\n'
            '  "tp1": 4077.50,\n'
            '  "sl": 4073.50,\n'
            '  "rr": "1:2",\n'
            '  "note": "سبب الدخول باختصار"\n'
            "}"
        )

        payload = {
            "model": "google/gemini-2.5-flash",
            "max_tokens": 400,
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
            sl_raw = data.get("sl", 0.0)
            note = data.get("note", "")

            if action in ["BUY", "SELL"]:
                # تطبيق هامش الأمان (SL Buffer) لمنع ضرب الاستوبات السريعة
                if action == "BUY":
                    adjusted_sl = round(sl_raw - SL_BUFFER_PRICE, 2)
                else:
                    adjusted_sl = round(sl_raw + SL_BUFFER_PRICE, 2)

                text_msg = (
                    f"🎯 **توصية سكالبينج جاهزة للتنفيذ (XAU/USD):**\n\n"
                    f"• الاتجاه: **{action}**\n"
                    f"• سعر الدخول: `{entry}`\n"
                    f"• الهدف (TP1): `{tp1}`\n"
                    f"• الستوب الأساسي: `{sl_raw}`\n"
                    f"🛡️ **الستوب لوز المعدل (مع هامش الأمان):** `{adjusted_sl}`\n"
                    f"💡 **ملاحظة:** {note}\n\n"
                    f"👇 اضغط على الزر أدناه لتنفيذ الصفقة فوراً بحذافيرها على MT5:"
                )

                cbd = f"TRADE|{action}|{adjusted_sl}|{tp1}"
                keyboard = [
                    [InlineKeyboardButton(f"🚀 تنفيذ صفقة {action} الآن على MT5", callback_data=cbd)]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(text_msg, reply_markup=reply_markup, parse_mode="Markdown")
            else:
                await update.message.reply_text(f"🎯 **توصية سكالبينج (XAU/USD):**\n\n• التوصية: **انتظار (WAIT)**\n💡 **السبب:** {note}")

        else:
            await update.message.reply_text(f"⚠️ خطأ من الذكاء الاصطناعي: {str(response)}")

    except Exception as e:
        await update.message.reply_text(f"⚠️ حدث خطأ في تحليل التوصية: {str(e)}")

# ---------------------------------------------------------
# 6. معالجة نقرة زر التنفيذ التفاعلي
# ---------------------------------------------------------
async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    if data[0] == "TRADE":
        action = data[1]
        sl = float(data[2])
        tp = float(data[3])

        await query.edit_message_reply_markup(reply_markup=None) # إخفاء الزر لمنع التكرار
        await query.message.reply_text(f"⏳ جاري إرسال صفقة {action} فوراً لمنصة MetaTrader 5...")

        # تنفيذ الصفقة على منصة MT5
        success, msg = execute_mt5_order(action, sl, tp)

        if success:
            await query.message.reply_text(f"✅ {msg}\n🛑 SL: `{sl}`\n🎯 TP: `{tp}`", parse_mode="Markdown")
        else:
            await query.message.reply_text(f"❌ لم تتم الصفقة: {msg}")

# ---------------------------------------------------------
# 7. التشغيل الرئيسي
# ---------------------------------------------------------
def main():
    keep_alive()
    init_mt5_connection()

    builder = Application.builder().token(BOT_TOKEN)
    application = builder.build()

    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(handle_button_click))

    print("🚀 البوت متصل ومستعد لتنفيذ الصفقات بنقرة زر...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, close_loop=False)

if __name__ == '__main__':
    main()
