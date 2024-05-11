import os
import requests
from mutagen.mp4 import MP4, MP4Cover
from yt_dlp import YoutubeDL
import telebot
from webserver import keep_alive

# Replace YOUR_BOT_TOKEN with your actual Telegram Bot token
BOT_TOKEN = os.environ["BOT_TOKEN"]
bot = telebot.TeleBot(BOT_TOKEN)

# Dictionary to store user states
user_states = {}

# Define a list to store filenames of files being processed
processing_files = []

def cleanup():
    # Delete any temporary files in the current directory
    for filename in os.listdir():
        if filename.endswith(".jpg") or filename.endswith(".m4a") or filename.endswith(".mp3") or filename.endswith(".mp4") or filename.endswith(".webm"):
            if filename not in processing_files:  # Check if the file is not currently being processed
                os.remove(filename)

def download_song(url, chat_id, message_id):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',
    }

    with YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            bot.edit_message_text(f"Song downloaded successfully as: {filename}", chat_id, message_id)
            return filename, info
        except Exception as e:
            bot.edit_message_text(f"Error downloading the song: {str(e)}", chat_id, message_id)
            return None, None

def add_metadata(json_data, song_filename, chat_id, message_id):
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
        bot.edit_message_text(f"Error adding metadata: {str(e)}", chat_id, message_id)

def extract_json(url, chat_id, message_id):
    ydl_opts = {
        'skip_download': True,  # Skip downloading the video
        'print_json': True
    }

    with YoutubeDL(ydl_opts) as ydl:
        try:
            result = ydl.extract_info(url, download=False)
            bot.edit_message_text("JSON metadata extracted successfully!", chat_id, message_id)
            return result
        except Exception as e:
            bot.edit_message_text(f"Error extracting JSON metadata: {str(e)}", chat_id, message_id)
            return None

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_states[message.chat.id] = {"downloading": False}
    bot.reply_to(message, "Hello! Please send me a song URL")

@bot.message_handler(func=lambda message: True)
def handle_song_url(message):
    chat_id = message.chat.id
    if user_states[chat_id]["downloading"]:
        bot.reply_to(message, "Sorry, I'm currently processing another request. Please wait.")
        return

    user_states[chat_id]["downloading"] = True
    url = message.text

    # Check if the URL is a playlist URL
    if "playlist" in url.lower():
        bot.reply_to(message, "Sorry, I cannot process playlist URLs. Please send me a single song URL.")
        user_states[chat_id]["downloading"] = False
        return

    sent_message = bot.send_message(chat_id, "Processing...")

    json_data = extract_json(url, chat_id, sent_message.id)
    if json_data:
        filename, info = download_song(url, chat_id, sent_message.id)
        if filename:
            add_metadata(json_data, filename, chat_id, sent_message.id)
            with open(filename, 'rb') as song_file:
                caption = f"{info['title']} - {info['abr']} kbps" if 'abr' in info else info['title']
                bot.send_audio(chat_id, song_file, title=info["title"], performer=info.get("artist", "Unknown Artist"), caption=caption)
            os.remove(filename)
            bot.delete_message(chat_id, sent_message.id)
    else:
        bot.edit_message_text("Error: Unable to extract metadata or download the song.", chat_id, sent_message.id)
    
    user_states[chat_id]["downloading"] = False

# Cleanup at the beginning of the script
cleanup()

keep_alive()
# Start the bot and keep it running
while True:
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        # Log the error
        print(f"Error occurred while polling: {str(e)}")
