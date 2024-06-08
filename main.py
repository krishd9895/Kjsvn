import os
import yt_dlp
import re
import sys
import traceback
import requests
import time
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from yt_dlp import YoutubeDL
from pyrogram import Client, filters
from pyrogram.types import Message
from mutagen.mp4 import MP4, MP4Cover
from webserver import keep_alive

# Load API credentials from environment variables
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Initialize the bot
app = Client("yt_audio_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Handle /start command
@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    start_message = "Please send Url.."
    await message.reply_text(start_message, disable_web_page_preview=True)



# Cleanup function
def cleanup():
    # Delete any files in the downloads directory
    for filename in os.listdir(DOWNLOADS_FOLDER):
        file_path = os.path.join(DOWNLOADS_FOLDER, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)



# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler("logs.txt", maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Handle /restart command
@app.on_message(filters.command("restart") & filters.private)
async def restart_command(client, message):
    await message.reply_text("Restarting the bot...")
    await asyncio.sleep(1)  # Add a short delay to ensure the reply is sent before restarting
    await restart_bot(message.chat.id)

# Handle /logs command
@app.on_message(filters.command("logs") & filters.private)
async def logs_command(client, message):
    with open("logs.txt", "rb") as file:
        await message.reply_document(document=file)

# Function to restart the bot
async def restart_bot(chat_id):
    python = sys.executable
    os.execl(python, python, *sys.argv)



# Handle /clean command
@app.on_message(filters.command("clean") & filters.private)
async def clean_command(client, message):
    cleanup()
    await message.reply_text("Cleanup completed successfully.")


# yt-dlp options for best audio download
ydl_opts = {
    'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best',
    'outtmpl': 'downloads/%(title)s.%(ext)s',
}

DOWNLOADS_FOLDER = "downloads"
url_pattern = r"^(https?://)?[^\s]+$"
user_states = {}

def sanitize_filename(filename):
    disallowed_chars = r'[\\/:*?"<>|]'
    return re.sub(disallowed_chars, '_', filename)


def is_playlist(url):
    with yt_dlp.YoutubeDL() as ydl:
        info_dict = ydl.extract_info(url, download=False)
        return 'entries' in info_dict

async def run_sync_in_executor(sync_func, *args):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sync_func, *args)

# Update the download_and_add_metadata function to return the downloaded filename along with the sanitized filename
async def download_and_add_metadata(url, chat_id, sent_message):
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]',
        'outtmpl': os.path.join(DOWNLOADS_FOLDER, '%(title)s.%(ext)s'),
    }

    def sanitize_filename(filename):
        disallowed_chars = r'[\\/:*?"<>|]'
        return re.sub(disallowed_chars, '_', filename)

    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            sanitized_filename = sanitize_filename(info.get('title', 'unknown')) + '.' + info.get('ext', 'mp3')
            downloaded_filename = ydl.prepare_filename(info)

            # Check if the file was downloaded successfully
            if os.path.exists(downloaded_filename):
                # Rename the downloaded file to the sanitized filename
                os.rename(downloaded_filename, os.path.join(DOWNLOADS_FOLDER, sanitized_filename))

                # Add metadata to the downloaded song
                file_path = os.path.join(DOWNLOADS_FOLDER, sanitized_filename)
                try:
                    audio = MP4(file_path)
                    audio["\xa9nam"] = info.get("title", "Unknown Title")
                    audio["\xa9ART"] = info.get("artist", "Unknown Artist")
                    audio["\xa9alb"] = info.get("album", "Unknown Album")
                    audio["\xa9day"] = str(info.get("release_year", "Unknown Year"))
                    audio.save()
                except Exception as e:
                    logging.error(f"Error adding metadata: {str(e)}")

                return sanitized_filename, info
            else:
                logging.warning(f"File not found: {downloaded_filename}.")
                return None, None
        except Exception as e:
            logging.error(f"Error downloading or adding metadata to the song: {str(e)}")
            return None, None


# Handle song URLs
@app.on_message(filters.text & filters.regex(url_pattern))
async def handle_song_url(client, message):
    chat_id = message.chat.id
    if user_states.get(chat_id, {}).get("downloading"):
        await message.reply_text("Sorry, I'm currently processing another request. Please wait.")
        return

    user_states[chat_id] = {"downloading": True}
    url = message.text

    # Check if the URL is a playlist URL
    if "playlist" in url.lower():
        await message.reply_text("Sorry, I cannot process playlist URLs. Please send me a single song URL.")
        user_states[chat_id]["downloading"] = False
        return

    sent_message = await message.reply_text("Processing...")

    # Download and add metadata to the song
    filename, info = await download_and_add_metadata(url, chat_id, sent_message)
    if filename and info:
        file_path = os.path.join(DOWNLOADS_FOLDER, filename)
        if os.path.exists(file_path):
            with open(file_path, 'rb') as song_file:
                caption = f"{info['title']} - {info.get('abr', 'Unknown Bitrate')} kbps"
                await app.send_audio(chat_id, song_file, title=info["title"], performer=info.get("artist", "Unknown Artist"), caption=caption)

                # Remove the file after uploading
                os.remove(file_path)
        else:
            logging.error(f"File not found: {file_path}")
        await sent_message.delete()
    else:
        await sent_message.edit_text("Error: Unable to download or add metadata to the song.")

    user_states[chat_id]["downloading"] = False

keep_alive()

if __name__ == "__main__":
    if not os.path.exists(DOWNLOADS_FOLDER):
        os.makedirs(DOWNLOADS_FOLDER)
    app.run()
