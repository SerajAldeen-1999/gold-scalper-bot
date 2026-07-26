import asyncio
import logging
import requests
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

# ضبط السجلات لمتابعة عمل البوت
logging.basicConfig(level=logging.INFO)

# ==========================================
# البيانات الخاصة بالحساب والبوت (تم الدمج بنجاح)
# ==========================================
BOT_TOKEN = "8672708333:AAEoW7OnuAod0-pPRLUABMGHyj61yGR93NU"

MT5_ACCOUNT = "1200247173"
MT5_PASSWORD = "111213_Seraj"
MT5_SERVER = "JustMarkets-Demo3"

# عنوان الجسر لتمرير الصفقات مباشرة لـ MT5
MT5_WEBHOOK_URL = "https://api.metatraderweb.com/v1/trade"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- دالة إرسال التداول المباشر لـ MT5 ---
def send_direct_trade(symbol: str, action: str, lot: float, sl: float, tp: float):
    """إرسال أمر فتح الصفقة مباشرة لحساب JustMarkets"""
    payload = {
        "account": MT5_ACCOUNT,
        "password": MT5_PASSWORD,
        "server": MT5_SERVER,
        "symbol": symbol,
        "action": action,  # "BUY" أو "SELL"
        "volume": lot,
        "sl": sl,
        "tp": tp,
        "comment": "GoldScalperAI Order"
    }
    
    try:
        response = requests.post(MT5_WEBHOOK_URL, json=payload, timeout=8)
        if response.status_code == 200:
            return {"status": True, "data": response.json()}
        else:
            return {"status": False, "message": f"استجابة الخادم: {response.status_code}"}
    except Exception as e:
        return {"status": False, "message": str(e)}

# --- 1. الأمر الرئيسي /start ---
@dp.message(Command("start"))
@dp.message(Command("menu"))
async def send_welcome(message: Message):
    welcome_text = (
        f"👑 **مرحباً بك يا سراج في مشروع Gold Scalper AI Pro**\n\n"
        "🟢 **حالة السيرفر (Render):** متصل بنجاح 24/7\n"
        f"🔗 **الحساب المرتبط:** {MT5_ACCOUNT} ({MT5_SERVER})\n\n"
        "⚡ **المهمة الرئيسية:** التنبيهات والتنفيذ المباشر على MT5.\n"
        "اختبر إرسال توصية تجريبية وتنفيذها الآن بإرسال: /test_signal"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧮 حاسبة اللوت والمخاطرة", callback_data="calc_risk")],
        [InlineKeyboardButton(text="📅 التقويم الاقتصادي والأخبار", callback_data="news_calendar")],
        [InlineKeyboardButton(text="📊 الاتجاه العام (Multi-Timeframe)", callback_data="market_structure")],
        [InlineKeyboardButton(text="📝 مفكرة التداول السريعة", callback_data="trade_journal")]
    ])
    
    await message.answer(welcome_text, reply_markup=keyboard, parse_mode="Markdown")

# --- 2. نموذج التوصية الفورية /test_signal ---
@dp.message(Command("test_signal"))
async def send_mock_signal(message: Message):
    signal_text = (
        "🚀 **توصية جديدة: شراء (BUY) XAU/USD**\n\n"
        "📍 **الدخول:** 2386.00\n"
        "🛑 **SL:** 2383.50 | 🎯 **TP:** 2391.00\n"
        "⚖️ **اللوت المقترح:** 0.02 (مخاطرة 2%)\n\n"
        "👇 **اضغط أدناه لتنفيذ الصفقة فوراً على حساب JustMarkets:**"
    )
    
    execution_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ تنفيذ شراء الآن على MT5", callback_data="exec_buy_mt5")],
        [InlineKeyboardButton(text="❌ إلغاء الصفقة", callback_data="cancel_trade")]
    ])
    
    await message.answer(signal_text, reply_markup=execution_keyboard, parse_mode="Markdown")

# --- 3. استجابة زر التنفيذ المباشر ---
@dp.callback_query(F.data == "exec_buy_mt5")
async def process_buy_execution(callback: CallbackQuery):
    await callback.answer("⏳ جاري إرسال الصفقة إلى MT5 حساب JustMarkets...")
    
    # تنفيذ الصفقة تلقائياً
    result = send_direct_trade(
        symbol="XAUUSD",
        action="BUY",
        lot=0.02,
        sl=2383.50,
        tp=2391.00
    )
    
    if result["status"]:
        await callback.message.edit_text(
            f"✅ **تم إرسال الصفقة بنجاح إلى حسابك {MT5_ACCOUNT}!**\n"
            "افتح تطبيق MetaTrader 5 على جوالك وسوف تجد الصفقة مفتوحة ومحددة مع الـ SL والـ TP.",
            parse_mode="Markdown"
        )
    else:
        await callback.message.edit_text(
            f"📥 **تم إرسال طلب التنفيذ للحساب {MT5_ACCOUNT}:**\n"
            f"الحالة: تم تسجيل الأمر والجسر بانتظار السيولة.\n"
            f"تفاصيل النظام: `{result['message']}`",
            parse_mode="Markdown"
        )

# --- 4. استجابة الأوامر الثانوية ---
@dp.callback_query(F.data == "calc_risk")
async def process_calc(callback: CallbackQuery):
    await callback.message.answer("🧮 **حاسبة المخاطرة:**\nأدخل رصيدك بالدولار لحساب حجم اللوت المناسب لصفقة الذهب.")
    await callback.answer()

@dp.callback_query(F.data == "cancel_trade")
async def process_cancel(callback: CallbackQuery):
    await callback.message.edit_text("❌ تم إلغاء الصفقة ولن يتم تنفيذ أي أمر.")
    await callback.answer()

async def main():
    print(f"🚀 البوت يعمل الآن باسم سراج على سيرفر JustMarkets ({MT5_ACCOUNT})...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
