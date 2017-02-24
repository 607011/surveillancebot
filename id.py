#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import telepot
import time

bot = None


def handle(msg):
    content_type, chat_type, chat_id = telepot.glance(msg)
    print("Message from ID {}".format(chat_id))
    if content_type == "text":
        bot.sendMessage(chat_id, "Your ID: {}".format(chat_id))


def main(api_key):
    global bot
    bot = telepot.Bot(api_key)
    bot.message_loop(handle)
    print(bot.getMe())
    print("Listening ...")
    while True:
        time.sleep(10)


if __name__ == "__main__":
    main(sys.argv[1])

