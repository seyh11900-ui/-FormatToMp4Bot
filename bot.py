import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from deep_translator import GoogleTranslator

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is missing!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_languages = {}
DEFAULT_LANG = "en"

LANGUAGES = {
    "en": "🇬🇧 English",
    "km": "🇰🇭 Khmer",
    "zh-CN": "🇨🇳 Chinese (Simplified)",
    "es": "🇪🇸 Spanish",
    "fr": "🇫🇷 French",
    "ja": "🇯🇵 Japanese",
    "ru": "🇷🇺 Russian",
    "vi": "🇻🇳 Vietnamese",
    "th": "🇹🇭 Thai"
}

def get_language_keyboard():
    buttons = []
    row = []
    for code, name in LANGUAGES.items():
        row.append(InlineKeyboardButton(text=name, callback_data=f"set_lang:{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    welcome_text = (
        f"👋 Hello, {message.from_user.first_name}!\n\n"
        "I am your automated translation bot.\n"
        "Send me any text message to translate it automatically, or select your target language below:"
    )
    await message.answer(welcome_text, reply_markup=get_language_keyboard())

@dp.message(Command("help"))
async def help_handler(message: types.Message):
    help_text = (
        "🤖 **Bot Usage & Commands:**\n\n"
        "• `/start` - Start the bot and select language\n"
        "• `/language` - Change your preferred target language\n"
        "• `/settings` - View current translation language\n"
        "• `/reset` - Reset language to default (English)\n"
        "• `/help` - Show this menu\n\n"
        "💡 *Tip:* Send any plain text message to receive an instant translation!"
    )
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(Command("language"))
async def language_handler(message: types.Message):
    await message.answer("Choose your preferred target language:", reply_markup=get_language_keyboard())

@dp.message(Command("settings"))
async def settings_handler(message: types.Message):
    chat_id = message.chat.id
    current_code = user_languages.get(chat_id, DEFAULT_LANG)
    lang_name = LANGUAGES.get(current_code, current_code)
    
    settings_text = (
        "⚙️ **Current Settings:**\n\n"
        f"• Target Language: **{lang_name}**\n\n"
        "Use `/language` to change your selection."
    )
    await message.answer(settings_text, parse_mode="Markdown")

@dp.message(Command("reset"))
async def reset_handler(message: types.Message):
    chat_id = message.chat.id
    user_languages[chat_id] = DEFAULT_LANG
    default_name = LANGUAGES.get(DEFAULT_LANG, DEFAULT_LANG)
    
    await message.answer(
        f"🔄 Target language reset to default: **{default_name}**",
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("set_lang:"))
async def set_language_callback(callback: types.CallbackQuery):
    lang_code = callback.data.split(":")[1]
    chat_id = callback.message.chat.id
    user_languages[chat_id] = lang_code
    
    lang_name = LANGUAGES.get(lang_code, lang_code)
    await callback.message.edit_text(
        f"✅ Target language set to: **{lang_name}**\n\n"
        "Send me any text message and I will translate it for you!",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(F.text & ~F.text.startswith("/"))
async def translate_message(message: types.Message):
    chat_id = message.chat.id
    target_lang = user_languages.get(chat_id, DEFAULT_LANG)

    try:
        translated_text = await asyncio.to_thread(
            lambda: GoogleTranslator(source='auto', target=target_lang).translate(message.text)
        )
        
        dest_lang = LANGUAGES.get(target_lang, target_lang.upper())

        response_text = (
            f"🔤 **Translation (➔ {dest_lang}):**\n\n"
            f"{translated_text}"
        )
        await message.reply(response_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Translation error: {e}")
        await message.reply("⚠️ An error occurred while translating. Please try again later.")

async def setup_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Start bot & select language"),
        BotCommand(command="language", description="Change target language"),
        BotCommand(command="settings", description="View current configuration"),
        BotCommand(command="reset", description="Reset language to default"),
        BotCommand(command="help", description="How to use this bot"),
    ]
    await bot.set_my_commands(commands)

async def main():
    logging.info("Starting Telegram Bot...")
    await bot.delete_webhook(drop_pending_updates=True)
    await setup_bot_commands(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
