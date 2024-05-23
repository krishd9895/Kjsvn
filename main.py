import os
import re
import requests
import asyncio
from mutagen.mp4 import MP4, MP4Cover
from yt_dlp import YoutubeDL
from pyrogram import Client, filters
from jiosaavn import JioSaavn
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import uuid



# Initialize Pyrogram Client
API_ID = os.environ["API_ID"]
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Initialize JioSaavn
saavn = JioSaavn()

# Dictionary to store user states
user_states = {}

# Define a list to store filenames of files being processed
processing_files = []

# Dictionary to store mapping between unique IDs and song information
song_info_dict = {}


# Regular expression pattern to match URLs
url_pattern = re.compile(r'http\S+')

# Cleanup function
def cleanup():
    # Delete any temporary files in the current directory
    for filename in os.listdir():
        if filename.endswith(".jpg") or filename.endswith(".m4a") or filename.endswith(".mp3") or filename.endswith(".mp4") or filename.endswith(".mkv") or filename.endswith(".webm"):
            if filename not in processing_files:  # Check if the file is not currently being processed
                os.remove(filename)

# Handle start command
@app.on_message(filters.command("start"))
async def send_welcome(client, message):
    user_states[message.chat.id] = {"downloading": False}
    await message.reply("Hello! Please send me a song URL or song name")

# Handle messages containing URLs
@app.on_message(filters.regex(url_pattern))
async def handle_message(client, message):
    chat_id = message.chat.id
    if chat_id not in user_states:
        user_states[chat_id] = {"downloading": False}

    if user_states[chat_id]["downloading"]:
        await message.reply("Sorry, I'm currently processing another request. Please wait.")
        return

    user_states[chat_id]["downloading"] = True
    
    # Find all URLs in the message
    urls = url_pattern.findall(message.text)

    for url in urls:
        # Check if the URL is a playlist URL
        if "playlist" in url.lower():
            await message.reply("Sorry, I cannot process playlist URLs. Please send me a single song URL.")
            continue

        sent_message = await message.reply("Processing...")

        # Extract metadata from the URL
        json_data = await extract_json(url, chat_id, sent_message.id)
        if json_data:
            filename, info = await download_song(url, chat_id, sent_message.id)
            if filename:
                await add_metadata(json_data, filename, chat_id, sent_message.id)
                with open(filename, 'rb') as song_file:
                    caption = f"{info['title']} - {info['abr']} kbps" if 'abr' in info else info['title']
                    await message.reply_audio(song_file, title=info["title"], performer=info.get("artist", "Unknown Artist"), caption=caption)
                os.remove(filename)
                await sent_message.delete()
        else:
            await sent_message.edit("Error: Unable to extract metadata or download the song.")

    user_states[chat_id]["downloading"] = False

# Define a handler for text messages
@app.on_message(~filters.regex(url_pattern))
async def handle_text_message(client, message):
    chat_id = message.chat.id
    if chat_id not in user_states:
        user_states[chat_id] = {"downloading": False}

    song_name = message.text
    await search_and_send_results(message.chat.id, song_name)
    



# Function to search for songs and send results
async def search_and_send_results(chat_id, song_name, number_of_results=3):
    data = await saavn.search_songs(song_name)

    if data and 'data' in data and data['data']:
        results = data['data'][:number_of_results]  # Get only the required number of results

        for result in results:
            title = result.get('title', '')
            album = result.get('album', '')
            url = result.get('url', '')
            primary_artists = result['more_info'].get('primary_artists', '')
            language = result['more_info'].get('language', '')

            # Generate a unique ID and store song information
            unique_id = str(uuid.uuid4())
            song_info_dict[unique_id] = {"url": url, "primary_artists": primary_artists}

            # Create an inline keyboard button for downloading the song
            download_button = InlineKeyboardButton("Download", callback_data=f"download|{unique_id}")
            reply_markup = InlineKeyboardMarkup([[download_button]])

            response = f"Title: {title}\nAlbum: {album}\nPrimary Artists: {primary_artists}\nLanguage: {language}"
            await app.send_message(chat_id, response, reply_markup=reply_markup)

# Handle button clicks
@app.on_callback_query(filters.regex(r"^download\|"))
async def download_callback(client, callback_query):
    chat_id = callback_query.message.chat.id
    data = callback_query.data.split("|")
    unique_id = data[1]

    if unique_id not in song_info_dict:
        await callback_query.answer("Invalid song ID", show_alert=True)
        return

    url = song_info_dict[unique_id]["url"]
    primary_artists = song_info_dict[unique_id]["primary_artists"]

    # Rest of the code remains the same...
    if chat_id not in user_states:
        user_states[chat_id] = {"downloading": False}

    if user_states[chat_id]["downloading"]:
        await callback_query.answer("Sorry, I'm currently processing another request. Please wait.", show_alert=True)
        return

    user_states[chat_id]["downloading"] = True

    sent_message = await callback_query.message.reply("Processing...")

    # Extract metadata from the URL
    json_data = await extract_json(url, chat_id, sent_message.id)
    if json_data:
        filename, info = await download_song(url, chat_id, sent_message.id)
        if filename:
            json_data["artist"] = primary_artists  # Set the primary artists info
            await add_metadata(json_data, filename, chat_id, sent_message.id)
            with open(filename, 'rb') as song_file:
                caption = f"{info['title']} - {info['abr']} kbps" if 'abr' in info else info['title']
                await callback_query.message.reply_audio(song_file, title=info["title"], performer=info.get("artist", "Unknown Artist"), caption=caption)
            os.remove(filename)
            await sent_message.delete()
    else:
        await sent_message.edit("Error: Unable to extract metadata or download the song.")

    user_states[chat_id]["downloading"] = False
    await callback_query.answer()    

# Function to download song from URL
async def download_song(url, chat_id, message_id):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',
    }

    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            await app.edit_message_text(chat_id, message_id, f"Uploading as: {filename}")
            return filename, info
        except Exception as e:
            await app.edit_message_text(chat_id, message_id, f"Error downloading the song: {str(e)}")
            return None, None

# Function to add metadata to downloaded song
async def add_metadata(json_data, song_filename, chat_id, message_id):
    try:
        # Add metadata to the downloaded song
        audio = MP4(song_filename)
        audio["\xa9nam"] = json_data["title"]
        audio["\xa9ART"] = json_data.get("artist", "Unknown Artist")
        audio["\xa9alb"] = json_data.get("album", "Unknown Album")
        audio["\xa9day"] = str(json_data.get("release_year", "Unknown Year"))
        audio.save()

        # Download thumbnail
        thumbnail_url = json_data["thumbnails"][0]["url"]
        thumbnail_response = requests.get(thumbnail_url)

        # Add thumbnail to the song file
        with open("temp.jpg", "wb") as f:
            f.write(thumbnail_response.content)

        audio["covr"] = [
            MP4Cover(open("temp.jpg", "rb").read(), MP4Cover.FORMAT_JPEG)
        ]
        audio.save()

        # Remove temporary thumbnail file
        os.remove("temp.jpg")
    except Exception as e:
        await app.edit_message_text(chat_id, message_id, f"Error adding metadata: {str(e)}")

# Function to extract JSON metadata from URL
async def extract_json(url, chat_id, message_id):
    ydl_opts = {
        'skip_download': True,  # Skip downloading the video
        'print_json': True
    }

    with YoutubeDL(ydl_opts) as ydl:
        try:
            result = ydl.extract_info(url, download=False)
            await app.edit_message_text(chat_id, message_id, "metadata extracted successfully!")
            return result
        except Exception as e:
            await app.edit_message_text(chat_id, message_id, f"Error extracting JSON metadata: {str(e)}")
            return None

# Cleanup at the beginning of the script
cleanup()

# Start the bot and keep it running
app.run()
