import os
import re
import requests
import asyncio
import logging
from mutagen.mp4 import MP4, MP4Cover
from yt_dlp import YoutubeDL
from pyrogram import Client, filters
from webserver import keep_alive

# Setup logging
logging.basicConfig(filename='logs.txt', level=logging.ERROR, format='%(asctime)s %(levelname)s:%(message)s')

# Create downloads folder if it doesn't exist
DOWNLOADS_FOLDER = "downloads"
if not os.path.exists(DOWNLOADS_FOLDER):
    os.makedirs(DOWNLOADS_FOLDER)

# Initialize Pyrogram Client
BOT_TOKEN = os.environ["BOT_TOKEN"]
api_id = os.environ["API_ID"]
api_hash = os.environ["API_HASH"]

app = Client("my_bot", bot_token=BOT_TOKEN, api_id=api_id, api_hash=api_hash)

# Dictionary to store user states
user_states = {}

# Regular expression pattern to match URLs
url_pattern = re.compile(r'^https?://\S+$')

# Cleanup function
def cleanup():
    # Delete any files in the downloads directory
    for filename in os.listdir(DOWNLOADS_FOLDER):
        file_path = os.path.join(DOWNLOADS_FOLDER, filename)
        if os.path.isfile(file_path):
            os.remove(file_path)

# Handle start command
@app.on_message(filters.command("start"))
async def send_welcome(client, message):
    user_states[message.chat.id] = {"downloading": False}
    await message.reply_text("Hello! Please send me a song URL")

# Handle clean command
@app.on_message(filters.command("clean"))
async def clean_downloads(client, message):
    cleanup()
    await message.reply_text("Downloads folder cleaned.")

# Handle logs command
@app.on_message(filters.command("logs"))
async def send_logs(client, message):
    chat_id = message.chat.id
    try:
        await client.send_document(chat_id, "logs.txt")
    except Exception as e:
        await message.reply_text(f"Error sending logs: {str(e)}")

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
            try:
                os.remove(file_path)
            except FileNotFoundError:
                logging.error(f"File not found: {file_path}")
        else:
            logging.error(f"File not found: {file_path}")
        await sent_message.delete()
    else:
        await sent_message.edit_text("Error: Unable to download or add metadata to the song.")

    user_states[chat_id]["downloading"] = False
    
# Function to download song from URL and add metadata
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
            filename = f"{sanitize_filename(info.get('title', 'unknown'))}.{info.get('ext', 'mp3')}"
            await sent_message.edit_text("Downloading and adding metadata...")

            # Add metadata to the downloaded song
            try:
                audio = MP4(os.path.join(DOWNLOADS_FOLDER, filename))
                audio["\xa9nam"] = info.get("title", "Unknown Title")
                audio["\xa9ART"] = info.get("artist", "Unknown Artist")
                audio["\xa9alb"] = info.get("album", "Unknown Album")
                audio["\xa9day"] = str(info.get("release_year", "Unknown Year"))
                audio.save()

                # Print the duration for debugging
                print_duration(filename)

                # Download thumbnail
                thumbnail_url = info.get("thumbnails", [{}])[0].get("url")
                if thumbnail_url:
                    thumbnail_response = requests.get(thumbnail_url)
                    if thumbnail_response.status_code == 200:
                        # Add thumbnail to the song file
                        with open(os.path.join(DOWNLOADS_FOLDER, "temp.jpg"), "wb") as f:
                            f.write(thumbnail_response.content)

                        audio["covr"] = [
                            MP4Cover(open(os.path.join(DOWNLOADS_FOLDER, "temp.jpg"), "rb").read(), MP4Cover.FORMAT_JPEG)
                        ]
                        audio.save()

                        # Remove temporary thumbnail file
                        os.remove(os.path.join(DOWNLOADS_FOLDER, "temp.jpg"))
            except Exception as e:
                logging.error(f"Error adding metadata: {str(e)}")
                print(f"Error adding metadata: {str(e)}")

            return filename, info
        except Exception as e:
            await sent_message.edit_text(f"Error: {str(e)}")
            logging.error(f"Error downloading or adding metadata to the song: {str(e)}")
            return None, None

# Function to print the duration of the audio file
def print_duration(song_filename):
    audio = MP4(os.path.join(DOWNLOADS_FOLDER, song_filename))
    duration = audio.info.length
    print(f"Duration: {duration} seconds")

# Cleanup at the beginning of the script
cleanup()
keep_alive()

# Start the bot and keep it running
while True:
    try:
        app.run()
    except Exception as e:
        logging.error(f"Error occurred while running the bot: {str(e)}")
        print(f"Error occurred while running the bot: {str(e)}")
