import os
import logging
import ffmpeg
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Read BOT_TOKEN from environment variables (Required for Railway/Render/Docker)
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Telegram Bot API standard download limit (20 MB)
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  

# Store user settings in-memory
USER_SETTINGS = {}

DEFAULT_PRESET = {
    "resolution": "original",  # Options: original, 720, 480
    "crf": "23",               # Lower CRF = better quality, larger size (18-28)
}


def get_user_settings(user_id: int) -> dict:
    """Retrieve or initialize settings for a given user."""
    if user_id not in USER_SETTINGS:
        USER_SETTINGS[user_id] = DEFAULT_PRESET.copy()
    return USER_SETTINGS[user_id]


# --- COMMAND HANDLERS ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responds to /start command."""
    welcome_text = (
        "👋 **Welcome to Video Converter Bot!**\n\n"
        "Send or forward any video file (MKV, AVI, MOV, WEBM, FLV, etc.), and I'll convert it to MP4.\n\n"
        "**Available Commands:**\n"
        "• `/start` - Start the bot\n"
        "• `/help` - Usage instructions and supported formats\n"
        "• `/settings` - Configure video resolution & quality\n"
        "• `/info` - Reply to a video to inspect file metadata"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responds to /help command."""
    help_text = (
        "ℹ️ **How to Use:**\n\n"
        "1. Send any video file (as a video message or document).\n"
        "2. The bot will automatically convert it to streaming-compatible MP4.\n"
        "3. Use `/settings` to change output resolution (e.g. 720p, 480p).\n"
        "4. Reply to any video message with `/info` to get detailed resolution, bitrate, and codec details.\n\n"
        "⚠️ **Note:** Telegram standard bot API limits downloads to 20 MB."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responds to /settings command with an interactive inline button menu."""
    user_id = update.effective_user.id
    settings = get_user_settings(user_id)

    res_label = settings["resolution"].upper() if settings["resolution"] != "original" else "Original"

    keyboard = [
        [
            InlineKeyboardButton(
                f"Resolution: {res_label}", callback_data="toggle_res"
            )
        ],
        [
            InlineKeyboardButton(
                f"Quality (CRF): {settings['crf']} (Medium)", callback_data="toggle_crf"
            )
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ **Conversion Settings**\n"
        "Click below to toggle preferences before sending a video:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles button clicks in the /settings menu."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    settings = get_user_settings(user_id)

    if query.data == "toggle_res":
        # Cycle resolutions: original -> 720 -> 480 -> original
        res_cycle = {"original": "720", "720": "480", "480": "original"}
        settings["resolution"] = res_cycle.get(settings["resolution"], "original")
    elif query.data == "toggle_crf":
        # Cycle CRF levels: 23 (Medium) -> 28 (Smaller File) -> 18 (High Quality) -> 23
        crf_cycle = {"23": "28", "28": "18", "18": "23"}
        settings["crf"] = crf_cycle.get(settings["crf"], "23")

    res_label = settings["resolution"].upper() if settings["resolution"] != "original" else "Original"
    crf_label = "High" if settings["crf"] == "18" else "Small File" if settings["crf"] == "28" else "Medium"

    keyboard = [
        [
            InlineKeyboardButton(
                f"Resolution: {res_label}", callback_data="toggle_res"
            )
        ],
        [
            InlineKeyboardButton(
                f"Quality: {crf_label} (CRF {settings['crf']})", callback_data="toggle_crf"
            )
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "⚙️ **Conversion Settings**\n"
        "Click below to toggle preferences before sending a video:",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responds to /info when replied to a video message."""
    reply = update.message.reply_to_message
    if not reply or not (reply.video or reply.document):
        await update.message.reply_text("⚠️ Please reply to a video message with `/info`.", parse_mode="Markdown")
        return

    media = reply.video or reply.document
    duration = getattr(media, "duration", "Unknown")
    file_size_mb = round((media.file_size or 0) / (1024 * 1024), 2)
    mime = getattr(media, "mime_type", "Unknown")

    info_text = (
        f"📊 **Video Metadata:**\n"
        f"• **Filename:** `{getattr(media, 'file_name', 'N/A')}`\n"
        f"• **Size:** {file_size_mb} MB\n"
        f"• **Duration:** {duration}s\n"
        f"• **MIME type:** `{mime}`"
    )
    await update.message.reply_text(info_text, parse_mode="Markdown")


# --- VIDEO CONVERSION HANDLER ---

async def process_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processes incoming video files based on configured user settings."""
    media = update.message.video or update.message.document
    if not media:
        await update.message.reply_text("❌ Please send a valid video file.")
        return

    if media.file_size and media.file_size > MAX_FILE_SIZE_BYTES:
        await update.message.reply_text(
            f"⚠️ File too large ({round(media.file_size / (1024*1024), 1)} MB). "
            f"Telegram Bot API limits downloads to 20 MB."
        )
        return

    status_msg = await update.message.reply_text("📥 Downloading video...")

    file_name = getattr(media, "file_name", "input_video") or "input_video"
    base_name, _ = os.path.splitext(file_name)

    telegram_file = await media.get_file()
    input_path = f"temp_{telegram_file.file_id}_{file_name}"
    output_path = f"converted_{telegram_file.file_id}_{base_name}.mp4"

    try:
        await telegram_file.download_to_drive(input_path)
        await status_msg.edit_text("⚙️ Converting video to MP4...")

        user_id = update.effective_user.id
        settings = get_user_settings(user_id)

        # Build FFmpeg options
        ffmpeg_stream = ffmpeg.input(input_path)
        
        # Resolution scaling logic
        vf_scale = None
        if settings["resolution"] == "720":
            vf_scale = "scale=-2:720"
        elif settings["resolution"] == "480":
            vf_scale = "scale=-2:480"

        output_kwargs = {
            "vcodec": "libx264",
            "acodec": "aac",
            "pix_fmt": "yuv420p",
            "preset": "fast",
            "crf": settings["crf"],
        }
        if vf_scale:
            output_kwargs["vf"] = vf_scale

        (
            ffmpeg_stream
            .output(output_path, **output_kwargs)
            .overwrite_output()
            .run(quiet=True)
        )

        await status_msg.edit_text("📤 Uploading converted MP4...")

        with open(output_path, "rb") as video_file:
            await update.message.reply_video(
                video=video_file,
                caption=f"✅ Done! (Res: {settings['resolution'].upper()}, CRF: {settings['crf']})",
                supports_streaming=True,
            )

        await status_msg.delete()

    except ffmpeg.Error as e:
        logging.error(f"FFmpeg conversion error: {e}")
        await status_msg.edit_text("❌ Failed to process video with FFmpeg.")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        await status_msg.edit_text("❌ An unexpected error occurred.")
    finally:
        for path in (input_path, output_path):
            if os.path.exists(path):
                os.remove(path)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fallback handler for invalid commands."""
    await update.message.reply_text(
        "❓ Unknown command. Type /start to see available commands."
    )


# --- MAIN ENGINE ---

def main():
    """Initializes and runs the Telegram bot."""
    if not BOT_TOKEN:
        raise ValueError(
            "CRITICAL: BOT_TOKEN environment variable is not set! "
            "Please set BOT_TOKEN in your environment variables or Railway settings."
        )

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register Command Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("info", info_command))

    # Register Callback Handler for Inline Settings Menu Buttons
    app.add_handler(CallbackQueryHandler(settings_callback))

    # Register Media Handler
    app.add_handler(
        MessageHandler(filters.VIDEO | filters.Document.VIDEO, process_video)
    )

    # Unknown Command Handler (Must be registered last)
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    print("Bot is up and responding to commands...")
    app.run_polling()


if __name__ == "__main__":
    main()
