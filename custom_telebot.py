import re
from telebot import TeleBot

class CustomTeleBot(TeleBot):
    def _test_filter(self, message_filter, filter_value, message):
        if message_filter == "regex":
            if message.content_type == 'text':
                return bool(re.search(filter_value, message.text))
            else:
                return False
        else:
            return super()._test_filter(message_filter, filter_value, message)
