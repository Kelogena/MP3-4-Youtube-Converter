from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import telegram.request
import yt_dlp
import os
import logging
import subprocess

# =========================
# CONFIG
# =========================
TOKEN = "8732078375:AAHqo9b67tUT_d8KwTTrsii3a7P8lVFkuPM"

DOWNLOAD_FOLDER = "downloads"
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# =========================
# FFMPEG
# =========================
FFMPEG_PATH = r"C:\ffmpeg\ffmpeg-8.1.1-essentials_build\bin"

MAX_VIDEO_SIZE = 49  # Telegram limit MB

logging.basicConfig(level=logging.INFO)

# =========================
# TELEGRAM SAFE REQUEST
# =========================
request = telegram.request.HTTPXRequest(
    connection_pool_size=8,
    read_timeout=300,
    write_timeout=300,
    connect_timeout=300,
)

# =========================
# START
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Надішли YouTube або TikTok URL 🎵📹"
    )

# =========================
# FIND LAST FILE
# =========================
def find_downloaded_file():

    files = os.listdir(DOWNLOAD_FOLDER)

    if not files:
        return None

    latest = max(
        [os.path.join(DOWNLOAD_FOLDER, f) for f in files],
        key=os.path.getctime
    )

    return latest

# =========================
# COMPRESS VIDEO
# =========================
def compress_video(input_path):

    output_path = input_path.replace(
        ".mp4",
        "_compressed.mp4"
    )

    ffmpeg = os.path.join(
        FFMPEG_PATH,
        "ffmpeg.exe"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-i", input_path,

        # scale down
        "-vf", "scale='min(1280,iw)':-2",

        # video codec
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "32",

        # audio codec
        "-c:a", "aac",
        "-b:a", "128k",

        output_path
    ]

    subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    return output_path

# =========================
# HANDLE URL
# =========================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):

    url = update.message.text.strip()

    context.user_data["url"] = url

    msg = await update.message.reply_text(
        "🔍 Отримую доступні якості..."
    )

    try:

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookiefile": "cookies.txt",
            "ffmpeg_location": FFMPEG_PATH,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                url,
                download=False
            )

        formats = info.get("formats", [])

        buttons = []
        added = set()

        # =========================
        # VIDEO FORMATS
        # =========================
        for f in reversed(formats):

            height = f.get("height")

            filesize = (
                f.get("filesize")
                or f.get("filesize_approx")
            )

            ext = f.get("ext")

            format_id = f.get("format_id")

            vcodec = f.get("vcodec")

            # only video
            if not height:
                continue

            if ext != "mp4":
                continue

            if vcodec == "none":
                continue

            if not filesize:
                continue

            size_mb = filesize / (1024 * 1024)

            # reserve for audio merge
            size_mb += 2

            # allow huge videos
            if size_mb > 2048:
                continue

            if height < 240:
                continue

            key = str(height)

            if key in added:
                continue

            added.add(key)

            # warning
            if size_mb > MAX_VIDEO_SIZE:

                text = (
                    f"📹 {height}p • "
                    f"{round(size_mb,1)} MB ⚠️"
                )

            else:

                text = (
                    f"📹 {height}p • "
                    f"{round(size_mb,1)} MB"
                )

            buttons.append([
                InlineKeyboardButton(
                    text,
                    callback_data=f"video|{format_id}"
                )
            ])

        # =========================
        # AUDIO SIZE
        # =========================
        duration = info.get("duration", 0)

        audio_mb = round(
            (duration * 192 / 8) / 1024,
            1
        )

        buttons.append([
            InlineKeyboardButton(
                f"🎵 MP3 • {audio_mb} MB",
                callback_data="audio"
            )
        ])

        if not buttons:

            raise Exception(
                "Немає доступних форматів"
            )

        await msg.edit_text(
            "Оберіть якість:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:

        logging.error(e)

        await msg.edit_text(f"❌ {e}")

# =========================
# SEND VIDEO
# =========================
async def send_video(query, path):

    with open(path, "rb") as f:

        await query.message.reply_video(
            video=f,
            supports_streaming=True,
            read_timeout=300,
            write_timeout=300,
            connect_timeout=300,
        )

# =========================
# SEND AUDIO
# =========================
async def send_audio(query, path):

    with open(path, "rb") as f:

        await query.message.reply_audio(
            audio=f,
            read_timeout=300,
            write_timeout=300,
            connect_timeout=300,
        )

# =========================
# BUTTON HANDLER
# =========================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query

    await query.answer()

    data = query.data

    url = context.user_data.get("url")

    if not url:

        await query.message.reply_text(
            "❌ URL not found"
        )

        return

    msg = await query.message.reply_text(
        "⏳ Завантаження..."
    )

    file_path = None

    try:

        # =========================
        # AUDIO
        # =========================
        if data == "audio":

            ydl_opts = {

                "format": "bestaudio/best",

                "outtmpl": os.path.join(
                    DOWNLOAD_FOLDER,
                    "%(title)s.%(ext)s"
                ),

                "quiet": True,
                "no_warnings": True,

                "cookiefile": "cookies.txt",

                "ffmpeg_location": FFMPEG_PATH,

                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }]
            }

        # =========================
        # VIDEO
        # =========================
        else:

            _, format_id = data.split("|")

            format_string = (
                f"{format_id}+bestaudio/"
                f"{format_id}"
            )

            ydl_opts = {

                "format": format_string,

                "merge_output_format": "mp4",

                "outtmpl": os.path.join(
                    DOWNLOAD_FOLDER,
                    "%(title)s.%(ext)s"
                ),

                "quiet": True,
                "no_warnings": True,

                "cookiefile": "cookies.txt",

                "ffmpeg_location": FFMPEG_PATH,
            }

        # =========================
        # DOWNLOAD
        # =========================
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            ydl.download([url])

        file_path = find_downloaded_file()

        if not file_path:

            raise Exception(
                "Файл не знайдено"
            )

        size_mb = (
            os.path.getsize(file_path)
            / (1024 * 1024)
        )

        # =========================
        # AUTO COMPRESS
        # =========================
        if data != "audio" and size_mb > MAX_VIDEO_SIZE:

            await msg.edit_text(
                f"🛠 Стискаю відео...\n"
                f"Було: {round(size_mb,1)} MB"
            )

            compressed_path = compress_video(
                file_path
            )

            if os.path.exists(compressed_path):

                try:
                    os.remove(file_path)
                except:
                    pass

                file_path = compressed_path

            size_mb = (
                os.path.getsize(file_path)
                / (1024 * 1024)
            )

            # still too big
            if size_mb > MAX_VIDEO_SIZE:

                raise Exception(
                    f"❌ Навіть після стискання "
                    f"файл {round(size_mb,1)} MB"
                )

        await msg.edit_text(
            "📤 Відправка..."
        )

        # =========================
        # SEND AUDIO
        # =========================
        if data == "audio":

            await send_audio(
                query,
                file_path
            )

        # =========================
        # SEND VIDEO
        # =========================
        else:

            await send_video(
                query,
                file_path
            )

        await msg.edit_text(
            "✔ Готово"
        )

    except Exception as e:

        logging.error(e)

        try:
            await msg.edit_text(
                "❌ Помилка"
            )
        except:
            pass

        await query.message.reply_text(
            f"❌ {e}"
        )

    finally:

        try:

            files = os.listdir(
                DOWNLOAD_FOLDER
            )

            for f in files:

                os.remove(
                    os.path.join(
                        DOWNLOAD_FOLDER,
                        f
                    )
                )

        except:
            pass

# =========================
# MAIN
# =========================
def main():

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .request(request)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle
        )
    )

    app.add_handler(
        CallbackQueryHandler(button)
    )

    print("🚀 BOT RUNNING")

    app.run_polling()

# =========================
# RUN
# =========================
if __name__ == "__main__":

    main()