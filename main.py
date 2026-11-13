import os
import io
import random
import aiohttp
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web, ClientTimeout
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

HORSE_SCENARIOS = [
    "standing on a sandy beach looking at the ocean", "in a dark foggy forest staring at the camera",
    "close-up portrait of a horse face", "sitting like a human on a wooden chair",
    "in a cyberpunk city at night, neon lights", "running through a snowy field far away",
    "eating hay in a dark barn", "in a desert with pyramids in the background",
    "looking through a window, sad mood", "in a deep space nebula, astronaut helmet"
]

RANDOM_CAPTIONS = [
    "нахуя", "сидит", "эчпочмак", "мда", "постирония", "бля", "конь в пальто", 
    "охуеть", "лошара", "пиздец", "че", "ок", "бетон", "хуета", "гойда", 
    "саси", "жиза", "база", "кринж", "слэй", "чей", "иди нахуй", "не читал", 
    "в рот топтал", "три рубля", "бля буду", "ну и хуй с ним", "похуй", 
    "даун", "лох", "я устал", "дай денег", "слышь", "эщкере", "чмо", "соси"
]

class MemeGen(StatesGroup):
    waiting_for_prompt = State()
    waiting_for_caption_choice = State()
    waiting_for_custom_caption = State()

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎨 Сделать коня", callback_data="make_meme")
    await message.answer("Йоу! Я генерю постироничных коней. Жми кнопку.", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "make_meme")
async def ask_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Опиши, че конь делает (например: 'стоит на берегу моря'). Или напиши 'рандом'.")
    await state.set_state(MemeGen.waiting_for_prompt)
    await callback.answer()

@dp.message(MemeGen.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    prompt_text = message.text.strip()
    if prompt_text.lower() == 'рандом':
        prompt_text = random.choice(HORSE_SCENARIOS)
    else:
        prompt_text = f"{prompt_text}, {random.choice(HORSE_SCENARIOS)}"

    full_prompt = f"{prompt_text}, low quality, dark lighting, 360p, shitpost style"
    await state.update_data(prompt=full_prompt)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🎲 Рандомная подпись", callback_data="random_caption")
    builder.button(text="✍️ Своя подпись", callback_data="custom_caption")
    
    await message.answer("Теперь подпись. Выбирай:", reply_markup=builder.as_markup())
    await state.set_state(MemeGen.waiting_for_caption_choice)

@dp.callback_query(MemeGen.waiting_for_caption_choice, F.data == "random_caption")
async def process_random_caption(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    prompt = data['prompt']
    caption = random.choice(RANDOM_CAPTIONS)
    await state.clear()
    await callback.answer()
    await generate_and_send(callback.message, prompt, caption)

@dp.callback_query(MemeGen.waiting_for_caption_choice, F.data == "custom_caption")
async def process_custom_caption_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Напиши свою подпись:")
    await state.set_state(MemeGen.waiting_for_custom_caption)
    await callback.answer()

@dp.message(MemeGen.waiting_for_custom_caption)
async def process_custom_caption(message: Message, state: FSMContext):
    data = await state.get_data()
    prompt = data['prompt']
    caption = message.text
    await state.clear()
    await generate_and_send(message, prompt, caption)

async def generate_and_send(message: Message, prompt: str, caption: str):
    msg = await message.answer("⏳ Генерирую шакального коня, подожди...")
    
    image_url = f"https://image.pollinations.ai/prompt/{prompt}?width=360&height=360&nologo=true&seed={random.randint(1, 999999)}"
    
    try:
        # Добавляем таймаут, чтобы бот не висел вечно, если сервер картинок тупит
        timeout = ClientTimeout(total=40)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    image_bytes = await resp.read()
                else:
                    await msg.edit_text("❌ Ошибка генерации картинки. Сервер прилег.")
                    return
    except asyncio.TimeoutError:
        await msg.edit_text("❌ Нейросеть затупила. Попробуй еще раз.")
        return
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка сети: {e}")
        return

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        
        # ОБРЕЗАЕМ ВОДЯНОЙ ЗНАК СНИЗУ
        img = img.crop((0, 0, img.width, img.height - 20))
        
        img = ImageEnhance.Color(img).enhance(0.4)
        img = ImageEnhance.Brightness(img).enhance(0.7)
        img = ImageEnhance.Contrast(img).enhance(0.6)
        img = img.resize((180, 180), Image.Resampling.NEAREST)
        img = img.resize((360, 340), Image.Resampling.NEAREST)

        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        except:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), caption, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        x = (img.width - text_width) / 2
        y = img.height - text_height - 15
        
        for adj_x in range(-2, 3):
            for adj_y in range(-2, 3):
                draw.text((x + adj_x, y + adj_y), caption, font=font, fill="black")
        draw.text((x, y), caption, font=font, fill="white")
        
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=30)
        output.seek(0)
        
        photo = BufferedInputFile(output.read(), filename="horse_meme.jpg")
        
        builder = InlineKeyboardBuilder()
        builder.button(text="🎲 Сгенерить ещё", callback_data="make_meme")
        builder.button(text="🔙 В меню", callback_data="back_to_menu")
        
        await message.answer_photo(photo, reply_markup=builder.as_markup())
        await msg.delete()
        
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка обработки картинки: {e}")

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎨 Сделать коня", callback_data="make_meme")
    await callback.message.edit_text("Главное меню:", reply_markup=builder.as_markup())
    await callback.answer()

# --- ЗАПУСК (RENDER) ---
async def on_startup(bot: Bot):
    # drop_pending_updates=True очищает всю очередь старых сообщений, чтобы бот не спамил
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)

async def on_shutdown(bot: Bot):
    await bot.delete_webhook()

def main():
    app = web.Application()
    # handle_in_background=True заставляет бота мгновенно отвечать Телеграму и не спамить
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot, handle_in_background=True)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    port = int(os.getenv("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
