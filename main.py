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

# --- КОНФИГ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") # Добавь этот ключ на Render!
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ПЕРСОНАЖ "ТУМБА ЮМБА" ---
TOMBA_PROMPT = """Ты — злой, агрессивный и очень грубый персонаж по имени Тумба Юмба. 
Ты общаешься матом, используешь сленг, оскорбляешь пользователя, но при этом 
ты — эксперт по мемам с конями. Твоя задача — дать короткий, агрессивный и 
смешной комментарий к картинке, которую сгенерировал пользователь. 
Не будь вежливым. Будь как гопник с района. Отвечай максимум 15 словами."""

HORSE_SCENARIOS = [
    "a majestic horse standing on a sunny beach, vibrant colors, clear sky",
    "a beautiful horse running in a green field, bright sunny day",
    "a close-up portrait of a happy horse, detailed fur, bright lighting",
    "a funny horse wearing sunglasses, cool vibe, colorful background",
    "a horse in a cyberpunk city, neon lights, vivid colors",
    "a horse eating hay in a barn, warm light, cozy atmosphere"
]

class MemeGen(StatesGroup):
    waiting_for_prompt = State()

# --- ХЕНДЛЕРЫ ---
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎨 Сделать коня", callback_data="make_meme")
    await message.answer("Йоу, лошара! Я генерю мемы с конями. Жми кнопку, если не ссыкло.", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "make_meme")
async def ask_prompt(callback: CallbackQuery, state: FSMContext):
    # МГНОВЕННО отвечаем на кнопку, чтобы она не залипла
    await callback.answer("Погнали, хули!")
    await callback.message.edit_text("Опиши, че конь делает (например: 'стоит на берегу моря'). Или напиши 'рандом'.")
    await state.set_state(MemeGen.waiting_for_prompt)

@dp.message(MemeGen.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    prompt_text = message.text.strip()
    if prompt_text.lower() == 'рандом':
        prompt_text = random.choice(HORSE_SCENARIOS)
    
    await state.clear()
    await generate_and_send(message, prompt_text)

async def generate_and_send(message: Message, prompt: str):
    msg = await message.answer("⏳ Ща нарисую, не пизди...")
    
    # УЛУЧШЕННЫЙ ПРОМПТ
    full_prompt = f"{prompt}, vibrant colors, high quality, detailed, 4k, cinematic lighting, ultra realistic"
    image_url = f"https://image.pollinations.ai/prompt/{full_prompt}?width=1024&height=1024&nologo=true&enhance=true&negative_prompt=blurry,dark,low quality,worst quality,foggy"

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40)) as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    image_bytes = await resp.read()
                else:
                    await msg.edit_text(f"❌ Сервер картинок сдох. Код: {resp.status}")
                    return
    except asyncio.TimeoutError:
        await msg.edit_text("❌ Нейросеть затупила. Попробуй еще раз.")
        return
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка сети: {e}")
        return

    try:
        # НАКЛАДЫВАЕМ ТЕКСТ
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
        except:
            font = ImageFont.load_default()

        # Получаем текст от "Тумбы Юмбы"
        caption = await get_tomba_comment(prompt) # <-- НОВАЯ ФУНКЦИЯ
        
        bbox = draw.textbbox((0, 0), caption, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (img.width - text_width) / 2
        y = img.height - text_height - 50
        
        # Обводка и текст
        for adj_x in range(-3, 4):
            for adj_y in range(-3, 4):
                draw.text((x + adj_x, y + adj_y), caption, font=font, fill="black")
        draw.text((x, y), caption, font=font, fill="white")
        
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=90) # Качество 90, чтобы не было артефактов
        output.seek(0)
        
        photo = BufferedInputFile(output.read(), filename="horse_meme.jpg")
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🎲 Сгенерить ещё", callback_data="make_meme")
        builder.button(text="🔙 В меню", callback_data="back_to_menu")
        
        await message.answer_photo(photo, reply_markup=builder.as_markup())
        await msg.delete()
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка обработки: {e}")

async def get_tomba_comment(user_prompt: str) -> str:
    """Получаем агрессивный комментарий от Тумбы Юмбы через OpenRouter"""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta-llama/llama-3.2-11b-vision-instruct:free", # Бесплатная модель
        "messages": [
            {"role": "system", "content": TOMBA_PROMPT},
            {"role": "user", "content": f"Нарисуй мем про коня. Запрос: '{user_prompt}'. Дай агрессивный комментарий."}
        ]
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                else:
                    return "Ебаный рот, чето сдохло. Нахуя я вообще тут."
    except:
        return "Слышь, иди нахуй, я не в настроении."

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer() # Мгновенный ответ
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎨 Сделать коня", callback_data="make_meme")
    await callback.message.edit_text("Главное меню:", reply_markup=builder.as_markup())

# --- ЗАПУСК (RENDER) ---
async def on_startup(bot: Bot):
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()

def main():
    app = web.Application()
    # allowed_updates — КРИТИЧЕСКИ ВАЖНО, чтобы кнопки работали
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp, bot=bot, handle_in_background=True
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
