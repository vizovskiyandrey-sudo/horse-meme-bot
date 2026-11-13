import os
import io
import random
import asyncio
import aiohttp
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
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

TOMBA_PROMPT = """Ты — злой, агрессивный и очень грубый персонаж по имени Тумба Юмба. 
Ты общаешься матом, используешь сленг, оскорбляешь пользователя. 
Дай короткий, агрессивный комментарий к картинке. Максимум 15 слов."""

HORSE_SCENARIOS = [
    "a majestic horse standing on a sunny beach, vibrant colors", 
    "a beautiful horse running in a green field, bright sunny day",
    "a funny horse wearing sunglasses, cool vibe, colorful background",
    "a horse in a cyberpunk city, neon lights, vivid colors",
    "a horse eating hay in a barn, warm light, cozy atmosphere"
]

# Если Тумба Юмба сломается, мы возьмем подпись отсюда
RANDOM_CAPTIONS = ["нахуя", "сидит", "эчпочмак", "мда", "постирония", "бля", "конь в пальто", "охуеть", "лошара", "пиздец"]

class MemeGen(StatesGroup):
    waiting_for_prompt = State()

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎨 Сделать коня", callback_data="make_meme")
    await message.answer("Йоу, лошара! Я генерю мемы с конями. Жми кнопку, если не ссыкло.", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "make_meme")
async def ask_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Погнали, хули!") 
    await callback.message.edit_text("Опиши, че конь делает (например: 'стоит на берегу моря'). Или напиши 'рандом'.")
    await state.set_state(MemeGen.waiting_for_prompt)

@dp.message(MemeGen.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    prompt_text = message.text.strip()
    if prompt_text.lower() == 'рандом':
        prompt_text = random.choice(HORSE_SCENARIOS)
    
    await state.clear()
    
    # ЖЕСТКО ЗАСТАВЛЯЕМ НЕЙРОСЕТЬ РИСОВАТЬ КОНЯ
    full_prompt = f"A high quality photo of a horse, {prompt_text}, vibrant colors, realistic, 8k, detailed"
    
    await generate_and_send(message, full_prompt)

async def generate_and_send(message: Message, full_prompt: str):
    msg = await message.answer("⏳ Ща нарисую, не пизди...")
    
    # Добавил seed, чтобы картинки не повторялись
    image_url = f"https://image.pollinations.ai/prompt/{full_prompt}?width=1024&height=1024&nologo=true&seed={random.randint(1, 999999)}"

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40)) as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    image_bytes = await resp.read()
                else:
                    await msg.edit_text(f"❌ Сервер картинок сдох. Код: {resp.status}")
                    return
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка сети: {e}")
        return

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
        except:
            font = ImageFont.load_default()

        # Получаем текст от Тумбы Юмбы (или рандомный, если он сдох)
        caption = await get_tomba_comment(full_prompt)
        
        bbox = draw.textbbox((0, 0), caption, font=font)
        x = (img.width - (bbox[2] - bbox[0])) / 2
        y = img.height - (bbox[3] - bbox[1]) - 50
        
        for adj_x in range(-3, 4):
            for adj_y in range(-3, 4):
                draw.text((x + adj_x, y + adj_y), caption, font=font, fill="black")
        draw.text((x, y), caption, font=font, fill="white")
        
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=90)
        output.seek(0)
        
        photo = BufferedInputFile(output.read(), filename="horse_meme.jpg")
        
        # ОСТАВЛЯЕМ ТОЛЬКО ОДНУ КНОПКУ
        builder = InlineKeyboardBuilder()
        builder.button(text="🎲 Сгенерить ещё", callback_data="make_meme")
        
        await message.answer_photo(photo, reply_markup=builder.as_markup())
        await msg.delete()
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка обработки: {e}")

async def get_tomba_comment(user_prompt: str) -> str:
    """Получаем агрессивный комментарий от Тумбы Юмбы"""
    if not OPENROUTER_API_KEY:
        return random.choice(RANDOM_CAPTIONS)
        
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    
    # ИСПОЛЬЗУЕМ НОРМАЛЬНУЮ ТЕКСТОВУЮ МОДЕЛЬ (а не vision)
    payload = {
        "model": "google/gemini-flash-1.5", 
        "messages": [
            {"role": "system", "content": TOMBA_PROMPT},
            {"role": "user", "content": f"Нарисуй мем про коня. Запрос: '{user_prompt}'."}
        ]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    # Если API сдох, просто берем рандомную подпись, чтобы не позориться
                    return random.choice(RANDOM_CAPTIONS)
    except:
        return random.choice(RANDOM_CAPTIONS)

# --- ЗАПУСК (Стандартный) ---
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()

def main():
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot) 
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
