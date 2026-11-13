import os
import io
import random
import asyncio
import aiohttp
import urllib.parse 
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

TOMBA_PROMPT = """Ты — злой, агрессивный персонаж Тумба Юмба. Общайся матом, коротко (до 15 слов). Ни в коем случае не используй словосочетание 'орешки макадамья'."""

LOCAL_DICT = {
    "дома": "at home in a cozy room", "в лесу": "in a dark pine forest", "на пляже": "on a sunny beach",
    "на траве": "on green grass", "на травке": "on green grass", "на поляне": "in a forest clearing",
    "в космосе": "in deep space", "на трамвае": "riding a vintage tram", "в машине": "inside a car",
    "в горах": "in the mountains", "в снегу": "in the snow", "в аду": "in hell with fire",
    "в офисе": "in a corporate office", "на луне": "on the moon", "в подвале": "in a dark basement",
    "на крыше": "on a rooftop", "в стиральной машине": "inside a washing machine",
    "на совещании": "at a business meeting wearing a suit", "в матрице": "inside the Matrix, green neon code",
    "на танке": "riding a military tank", "в туалете": "sitting on a toilet",
    "конь чистит картошку": "a horse peeling potatoes", "золотая картошка": "a giant golden potato",
    "орешки макадамья": "macadamia nuts", "в школе": "in a school classroom", "на диване": "on a cozy sofa",
    "в библиотеке": "in a grand library", "в баре": "in a dark pub", "на катке": "on an ice rink",
    "в самолете": "inside an airplane", "на корабле": "on a pirate ship", "в деревне": "in a rural village",
    "на балконе": "on a balcony", "в подъезде": "in a dirty stairwell", "на крыше небоскреба": "on a skyscraper roof",
    "в пустыне": "in a sandy desert", "в джунглях": "in a dense jungle", "под водой": "underwater in the ocean",
    "на вулкане": "on a volcano", "в магазине": "in a grocery store", "в спортзале": "in a gym",
    "на рок-концерте": "at a rock concert", "в кинотеатре": "in a cinema", "на кладбище": "in a creepy graveyard",
    "в пивной": "in a beer hall", "на кухне": "in a messy kitchen", "в спальне": "in a bedroom",
    "на заводе": "in a factory", "на стройке": "on a construction site", "на ферме": "on a farm",
    "в аэропорту": "in an airport terminal"
}

RANDOM_CAPTIONS = [
    "нахуя", "сидит", "эчпочмак", "мда", "постирония", "бля", "конь в пальто", "охуеть", "лошара", "пиздец", 
    "че", "ок", "бетон", "хуета", "гойда", "саси", "жиза", "база", "кринж", "слэй", "чей", "иди нахуй", 
    "не читал", "в рот топтал", "три рубля", "бля буду", "ну и хуй с ним", "похуй", "даун", "лох", "я устал", 
    "дай денег", "слышь", "эщкере", "чмо", "соси", "золотая картошка"
]

class MemeGen(StatesGroup):
    waiting_for_prompt = State()

# --- ФУНКЦИЯ ПОКАЗА МЕНЮШКИ (используется в двух местах) ---
async def show_location_menu(message: Message, state: FSMContext):
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
    builder.button(text="⛰ В горах", callback_data="loc_в горах")
    builder.button(text="❄️ В снегу", callback_data="loc_в снегу")
    builder.button(text="🔥 В аду", callback_data="loc_в аду")
    builder.button(text="🏢 В офисе", callback_data="loc_в офисе")
    builder.button(text="🌕 На луне", callback_data="loc_на луне")
    builder.button(text="🏘 На крыше", callback_data="loc_на крыше")
    builder.button(text="🥔 Конь чистит картошку", callback_data="loc_конь чистит картошку")
    builder.button(text="✍️ Свой вариант", callback_data="loc_custom")
    
    builder.adjust(2)
    await message.answer("Выбери локацию для коня (или напиши свой текст):", reply_markup=builder.as_markup())
    await state.set_state(MemeGen.waiting_for_prompt)

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🎨 Сделать коня", callback_data="make_meme")
    await message.answer("Йоу, лошара! Я генерю мемы с конями. Жми кнопку, если не ссыкло.", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "make_meme")
async def ask_prompt(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text("🎨 Погнали!")
    await show_location_menu(callback.message, state)

@dp.callback_query(F.data.startswith("loc_"))
async def process_location_callback(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    loc_key = callback.data.replace("loc_", "")
    
    if loc_key == "custom":
        await callback.message.edit_text("Напиши свой запрос (например, 'на трамвае'):")
        return
        
    await state.clear()
    await callback.message.edit_text(f"Выбрано: {loc_key}")
    await proceed_generation(callback.message, loc_key)

@dp.message(MemeGen.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext):
    prompt_text = message.text.strip().lower()
    await state.clear()
    await proceed_generation(message, prompt_text)

async def proceed_generation(message: Message, prompt_text: str):
    if prompt_text in LOCAL_DICT:
        english_prompt = LOCAL_DICT[prompt_text]
        msg = await message.answer(f"⏳ Нашел в словаре: {english_prompt}")
    else:
        msg = await message.answer("⏳ Слова нет в словаре, перевожу через интернет...")
        english_prompt = await translate_text(prompt_text)
        await msg.edit_text(f"⏳ Ща нарисую: {english_prompt}...")
    
    full_prompt = f"A high quality photo of a horse, {english_prompt}, vibrant colors, realistic, 8k, detailed"
    await generate_and_send(message, full_prompt, msg, prompt_text)

async def translate_text(text: str) -> str:
    try:
        url = f"https://lingva.ml/api/v1/ru/en/{urllib.parse.quote(text)}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return (await resp.json())["translation"]
    except Exception: pass

    try:
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text)}&langpair=ru|en"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    translated = (await resp.json())["responseData"]["translatedText"]
                    if translated and translated.lower() != text.lower():
                        return translated
    except Exception: pass

    return text 

async def fetch_image_from_apis(prompt: str):
    try:
        await asyncio.sleep(2)
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true&model=flux&seed={random.randint(1, 999999)}"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(url) as resp:
                if resp.status == 200: return await resp.read()
    except Exception: pass

    try:
        api_url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=50)) as session:
            async with session.post(api_url, json={"inputs": prompt}) as resp:
                if resp.status == 200: return await resp.read()
    except Exception: pass
    
    return None

async def generate_and_send(message: Message, full_prompt: str, status_msg: Message, original_prompt: str):
    image_bytes = await fetch_image_from_apis(full_prompt)

    if not image_bytes:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Попробовать снова (10с)", callback_data="retry_gen")
        await status_msg.edit_text("❌ Все сервера с картинками сдохли. Попробуй через 10 секунд.", reply_markup=builder.as_markup())
        asyncio.create_task(update_timer(status_msg.message_id, message.chat.id))
        return

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = img.crop((0, 0, img.width, img.height - 30))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 60)
        except:
            font = ImageFont.load_default()
        
        # ЛОГИКА ОРЕШКОВ МАКАДАМЬЯ
        macadamia_locations = ["в лесу", "на траве", "на травке", "на поляне", "в туалете"]
        if original_prompt in macadamia_locations:
            pool = RANDOM_CAPTIONS + ["орешки макадамья", "орешки макадамья"]
            caption = random.choice(pool)
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
        img.save(output, format="JPEG", quality=90)
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
    await callback.answer()
    await callback.message.edit_text("🔄 Окей, пробуем еще раз. Выбирай:")
    # ТУТ ВЫЗЫВАЕТСЯ МЕНЮШКА ВМЕСТО ПРОСЬБЫ НАПИСАТЬ ТЕКСТ
    await show_location_menu(callback.message, state)

async def get_tomba_comment(user_prompt: str) -> str:
    if not OPENROUTER_API_KEY: return random.choice(RANDOM_CAPTIONS)
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "google/gemini-flash-1.5", "messages": [{"role": "system", "content": TOMBA_PROMPT}, {"role": "user", "content": f"Запрос: '{user_prompt}'."}]}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    return (await resp.json())["choices"][0]["message"]["content"].strip()
                return random.choice(RANDOM_CAPTIONS)
    except: return random.choice(RANDOM_CAPTIONS)

async def health_check(request):
    return web.Response(text="OK")

async def main():
    print("Бот запущен!")
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
    asyncio.run(main())
