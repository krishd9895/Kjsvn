import os
import re
import requests
import asyncio
import logging
from mutagen.mp4 import MP4, MP4Cover
from yt_dlp import YoutubeDL
from pyrogram import Client, filters
from jiosaavn import JioSaavn
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

# Initialize JioSaavn
saavn = JioSaavn()

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

    # Extract metadata from the URL
    json_data = extract_json(url, chat_id, sent_message.message_id)
    if json_data:
        filename, info = await download_song(url, chat_id, sent_message.message_id)
        if filename:
            await add_metadata(json_data, filename, chat_id, sent_message.message_id)
            with open(os.path.join(DOWNLOADS_FOLDER, filename), 'rb') as song_file:
                caption = f"{info['title']} - {info['abr']} kbps" if 'abr' in info else info['title']
                await app.send_audio(chat_id, song_file, title=info["title"], performer=info.get("artist", "Unknown Artist"), caption=caption)
            os.remove(os.path.join(DOWNLOADS_FOLDER, filename))
            await app.delete_messages(chat_id, sent_message.message_id)
    else:
        await app.edit_message_text("Error: Unable to extract metadata or download the song.", chat_id, sent_message.message_id)

    user_states[chat_id]["downloading"] = False

# Define a handler for text messages
@app.on_message(filters.text & ~filters.regex(url_pattern))
async def handle_message(client, message):
    song_name = message.text
    await search_and_send_results(message.chat.id, song_name)

# Function to search for songs and send results
async def search_and_send_results(chat_id, song_name):
    data = await saavn.search_songs(song_name)

    if data and 'data' in data and data['data']:
        result = data['data']
        title = result.get('title', '')
        album = result.get('album', '')
        url = result.get('url', '')
        primary_artists = result['more_info'].get('primary_artists', '')
        language = result['more_info'].get('language', '')

        response = f"Title: {title}\nAlbum: {album}\nURL: {url}\nPrimary Artists: {primary_artists}\nLanguage: {language}"
        await app.send_message(chat_id, response)

# Function to download song from URL
async def download_song(url, chat_id, message_id):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(DOWNLOADS_FOLDER, '%(title)s.%(ext)s'),
    }

    def sanitize_filename(filename):
        # Define a regex pattern to match any character not allowed in filenames
        disallowed_chars = r'[\\/:*?"<>|]'
        # Replace disallowed characters with an underscore
        return re.sub(disallowed_chars, '_', filename)

    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            sanitized_filename = sanitize_filename(filename)
            os.rename(filename, sanitized_filename)  # Rename the file to the sanitized filename
            await app.edit_message_text(f"Uploading as: {sanitized_filename}", chat_id, message_id)
            return sanitized_filename, info
        except Exception as e:
            await app.edit_message_text(f"Error downloading the song: {str(e)}", chat_id, message_id)
            logging.error(f"Error downloading the song: {str(e)}")
            return None, None

# Function to add metadata to downloaded song
async def add_metadata(json_data, song_filename, chat_id, message_id):
    try:
        # Add metadata to the downloaded song
        audio = MP4(os.path.join(DOWNLOADS_FOLDER, song_filename))
        audio["\xa9nam"] = json_data["title"]
        audio["\xa9ART"] = json_data.get("artist", "Unknown Artist")
        audio["\xa9alb"] = json_data.get("album", "Unknown Album")
        audio["\xa9day"] = str(json_data.get("release_year", "Unknown Year"))
        audio.save()

        # Download thumbnail
        thumbnail_url = json_data["thumbnails"][0]["url"]
        thumbnail_response = requests.get(thumbnail_url)

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
        await app.edit_message_text(f"Error adding metadata: {str(e)}", chat_id, message_id)
        logging.error(f"Error adding metadata: {str(e)}")

# Function to extract JSON metadata from URL
def extract_json(url, chat_id, message_id):
    ydl_opts = {
        'skip_download': True,  # Skip downloading the video
        'print_json': True
    }

    with YoutubeDL(ydl_opts) as ydl:
        try:
            result = ydl.extract_info(url, download=False)
            app.edit_message_text("Metadata extracted successfully!", chat_id, message_id)
            return result
        except Exception as e:
            app.edit_message_text(f"Error extracting JSON metadata: {str(e)}", chat_id, message_id)
            logging.error(f"Error extracting JSON metadata: {str(e)}")
            return None

# Function to check if a string contains a URL
def contains_url(text):
    return bool(url_pattern.search(text))

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
