import os
import io
import random
import asyncio
import aiohttp
import urllib.parse 
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST") 
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

TOMBA_PROMPT = """Ты — злой, агрессивный персонаж Тумба Юмба. Общайся матом, коротко (до 15 слов)."""

LOCAL_DICT = {
    "дома": "at home in a cozy room", "в лесу": "in a dark pine forest", "на пляже": "on a sunny beach",
    "на траве": "on green grass", "на травке": "on green grass", "на поляне": "in a forest clearing",
    "в космосе": "in deep space", "на трамвае": "riding a vintage tram", "в машине": "inside a car",
    "в горах": "in the mountains", "в снегу": "in the snow", "в аду": "in hell with fire",
    "в офисе": "in a corporate office", "на луне": "on the moon", "в подвале": "in a dark basement",
    "на крыше": "on a rooftop", "в стиральной машине": "inside a washing machine",
    "на совещании": "at a business meeting wearing a suit", "в матрице": "inside the Matrix, green neon code",
    "на танке": "riding a military tank", "в туалете": "sitting on a toilet",
    "конь чистит картошку": "a horse peeling potatoes", "золотая картошка": "a giant golden potato"
}

RANDOM_CAPTIONS = ["нахуя", "сидит", "эчпочмак", "мда", "постирония", "бля", "конь в пальто", "охуеть", "лошара", "пиздец"]

class MemeGen(StatesGroup):
    waiting_for_prompt = State()

async def download_font():
    font_url = "https://github.com/google/fonts/raw/main/ofl/lobster/Lobster-Regular.ttf"
    if not os.path.exists("Lobster-Regular.ttf"):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(font_url) as resp:
                    if resp.status == 200:
                        with open("Lobster-Regular.ttf", 'wb') as f:
                            f.write(await resp.read())
        except Exception as e:
            print(f"Не удалось скачать шрифт: {e}")

def get_font(size):
    # Пытаемся взять Lobster, если нет - DejaVu
    try:
        return ImageFont.truetype("Lobster-Regular.ttf", size)
    except:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except:
            return ImageFont.load_default()

async def show_location_menu(message: Message, state: FSMContext):
    await state.clear() # Сбрасываем старые таймеры
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Дома", callback_data="loc_дома")
    builder.button(text="🌲 В лесу", callback_data="loc_в лесу")
    builder.button(text="🏖 На пляже", callback_data="loc_на пляже")
    builder.button(text="🚀 В космосе", callback_data="loc_в космосе")
    builder.button(text="🤖 В матрице", callback_data="loc_в матрице")
    builder.button(text="🪖 На танке", callback_data="loc_на танке")
    builder.button(text="🚽 В туалете", callback_data="loc_в туалете")
    builder.button(text="🧺 В стиралке", callback_data="loc_в стиральной машине")
    builder.button(text="💼 На совещании", callback_data="loc_на совещании")
    builder.button(text="🌿 На траве", callback_data="loc_на траве")
    builder.button(text="🍀 На травке", callback_data="loc_на травке")
    builder.button(text="🏞 На поляне", callback_data="loc_на поляне")
    builder.button(text="🥔 Конь чистит картошку", callback_data="loc_конь чистит картошку")
    builder.button(text="✍️ Свой вариант", callback_data="loc_custom")
    builder.adjust(2)
    await message.answer("Выбери локацию для коня:", reply_markup=builder.as_markup())
    await state.set_state(MemeGen.waiting_for_prompt)

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎨 Сделать коня", callback_data="make_meme")
    await message.answer("Йоу! Жми кнопку.", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "make_meme")
async def ask_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_location_menu(callback.message, state)

@dp.callback_query(F.data.startswith("loc_"))
async def process_location_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    loc_key = callback.data.replace("loc_", "")
    if loc_key == "custom":
        await callback.message.edit_text("Напиши свой запрос:")
        return
    await state.clear()
    await callback.message.edit_text(f"Выбрано: {loc_key}")
    await proceed_generation(callback.message, loc_key, state)

@dp.message(MemeGen.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    prompt_text = message.text.strip().lower()
    await state.clear()
    await proceed_generation(message, prompt_text, state)

async def proceed_generation(message: Message, prompt_text: str, state: FSMContext):
    english_prompt = LOCAL_DICT.get(prompt_text, prompt_text)
    msg = await message.answer(f"⏳ Ща нарисую: {english_prompt}...")
    
    full_prompt = f"A horse, {english_prompt}, low quality, blurry, shitpost, 360p, bad composition, funny"
    await generate_and_send(message, full_prompt, msg, prompt_text, state)

async def fetch_image_from_apis(prompt: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # 1. Pollinations
    try:
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true&model=flux&seed={random.randint(1, 999999)}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200: return await resp.read()
    except Exception: pass

    # 2. Airforce (Резерв)
    try:
        url = f"https://api.airforce/imagine?prompt={urllib.parse.quote(prompt)}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200: return await resp.read()
    except Exception: pass

    return None

async def generate_and_send(message: Message, full_prompt: str, status_msg: Message, original_prompt: str, state: FSMContext):
    image_bytes = await fetch_image_from_apis(full_prompt)
    
    if not image_bytes:
        img = Image.new('RGB', (1024, 1024), color='black')
        draw = ImageDraw.Draw(img)
        font = get_font(80)
        
        caption = "НЕЙРОНКА СДОХЛА"
        bbox = draw.textbbox((0, 0), caption, font=font)
        x = (img.width - (bbox[2] - bbox[0])) / 2
        y = (img.height - (bbox[3] - bbox[1])) / 2
        draw.text((x, y), caption, font=font, fill="red")
        
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=90)
        output.seek(0)
        photo = BufferedInputFile(output.read(), filename="fail.jpg")
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Попробовать снова (10с)", callback_data="retry_gen")
        
        fail_msg = await message.answer_photo(photo, caption="Сервера легли. Жди 10 секунд.", reply_markup=builder.as_markup())
        await status_msg.delete()
        
        retry_time = datetime.now() + timedelta(seconds=10)
        await state.update_data(retry_at=retry_time.timestamp())
        asyncio.create_task(update_timer(fail_msg.message_id, message.chat.id))
        return

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = img.crop((0, 0, img.width, img.height - 30))
        draw = ImageDraw.Draw(img)
        font = get_font(70)
        
        if original_prompt == "конь чистит картошку":
            if random.random() < 0.6: caption = "золотая картошка"
            else: caption = await get_tomba_comment(full_prompt)
        elif original_prompt in ["в лесу", "на траве", "на травке", "на поляне"]:
            roll = random.random()
            if roll < 0.45: caption = "спайс"
            elif roll < 0.90: caption = "орешки макадамья"
            else: caption = random.choice(RANDOM_CAPTIONS)
        else:
            caption = await get_tomba_comment(full_prompt)
        
        bbox = draw.textbbox((0, 0), caption, font=font)
        x = (img.width - (bbox[2] - bbox[0])) / 2
        y = img.height - (bbox[3] - bbox[1]) - 50
        
        for adj_x in range(-3, 4):
            for adj_y in range(-3, 4):
                draw.text((x + adj_x, y + adj_y), caption, font=font, fill="black")
        draw.text((x, y), caption, font=font, fill="white")
        
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=70)
        output.seek(0)
        
        photo = BufferedInputFile(output.read(), filename="horse_meme.jpg")
        builder = InlineKeyboardBuilder()
        builder.button(text="🎲 Сгенерить ещё", callback_data="make_meme")
        
        await message.answer_photo(photo, reply_markup=builder.as_markup())
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка обработки: {e}")

async def update_timer(message_id: int, chat_id: int):
    for seconds_left in range(9, 0, -1):
        await asyncio.sleep(1)
        builder = InlineKeyboardBuilder()
        builder.button(text=f"🔄 Попробовать снова ({seconds_left}с)", callback_data="retry_gen")
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=builder.as_markup())
        except: pass

@dp.callback_query(F.data == "retry_gen")
async def retry_generation(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    retry_at = data.get('retry_at', 0)
    remaining = int(retry_at - datetime.now().timestamp())
    
    if remaining > 0:
        await callback.answer()
        await callback.message.answer(f"ПОДОЖДИ ПИДОРАС, НЕЙРОНКИ ЛЕЖАТ, ОТДЫХАЮТ. ВОЗВРАЩАЙСЯ ЧЕРЕЗ {remaining} СЕКУНД.")
        return
        
    await callback.answer()
    # Удаляем сообщение с черным квадратом и отправляем меню заново
    await callback.message.delete()
    await show_location_menu(callback.message, state)

async def get_tomba_comment(user_prompt: str) -> str:
    if not OPENROUTER_API_KEY: return random.choice(RANDOM_CAPTIONS)
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "google/gemini-flash-1.5", "messages": [{"role": "system", "content": TOMBA_PROMPT}, {"role": "user", "content": f"Запрос: '{user_prompt}'."}]}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200: return (await resp.json())["choices"][0]["message"]["content"].strip()
                return random.choice(RANDOM_CAPTIONS)
    except: return random.choice(RANDOM_CAPTIONS)

async def on_startup(bot: Bot):
    await download_font()
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()
    await bot.session.close()

def main():
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.router.add_get('/', lambda r: web.Response(text="OK"))
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
