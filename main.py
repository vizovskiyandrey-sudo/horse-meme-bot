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
from aiohttp import web
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

TOMBA_PROMPT = """Ты — злой, агрессивный персонаж Тумба Юмба. Общайся матом, коротко (до 15 слов)."""
HORSE_SCENARIOS = ["standing on a sunny beach", "running in a green field", "wearing sunglasses", "in a cyberpunk city", "eating hay in a barn"]
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
    # Убрали всплывающий текст, просто моментально гасим кнопку
    await callback.answer()
    
    # Отправляем НОВОЕ сообщение (не редактируем старое с картинкой!), как ты и просил
    await callback.message.answer("да блять, давай загенерим, где сидеть ебучему коню?")
    await state.set_state(MemeGen.waiting_for_prompt)

@dp.message(MemeGen.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    prompt_text = message.text.strip()
    if prompt_text.lower() == 'рандом':
        prompt_text = random.choice(HORSE_SCENARIOS)
    await state.clear()
    
    full_prompt = f"A high quality photo of a horse, {prompt_text}, vibrant colors, realistic, 8k, detailed"
    await generate_and_send(message, full_prompt)

async def generate_and_send(message: Message, full_prompt: str):
    # Это сообщение мы потом удалим, чтобы не засорять чат
    msg = await message.answer("⏳ Ща нарисую, не пизди...")
    
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
        builder = InlineKeyboardBuilder()
        builder.button(text="🎲 Сгенерить ещё", callback_data="make_meme")
        
        # Отправляем картинку с кнопкой
        await message.answer_photo(photo, reply_markup=builder.as_markup())
        
        # Удаляем сообщение "Ща нарисую", чтобы было чисто
        await msg.delete()
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка обработки: {e}")

async def get_tomba_comment(user_prompt: str) -> str:
    if not OPENROUTER_API_KEY: return random.choice(RANDOM_CAPTIONS)
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "google/gemini-flash-1.5", "messages": [{"role": "system", "content": TOMBA_PROMPT}, {"role": "user", "content": f"Запрос: '{user_prompt}'."}]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                return random.choice(RANDOM_CAPTIONS)
    except:
        return random.choice(RANDOM_CAPTIONS)

async def health_check(request):
    return web.Response(text="OK")

async def main():
    print("Бот запущен через Long Polling на фоне!")
    await bot.delete_webhook(drop_pending_updates=True)
    
    asyncio.create_task(dp.start_polling(bot))
    
    app = web.Application()
    app.router.add_get('/', health_check)
    
    port = int(os.getenv("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    main()
