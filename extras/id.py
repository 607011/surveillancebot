#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import telepot
import time

bot = None


def handle(msg):
    content_type, chat_type, chat_id = telepot.glance(msg)
    if content_type == 'text':
        bot.sendChatAction(chat_id, action='typing')
        time.sleep(1.4)
        bot.sendMessage(chat_id, 'Your ID: {}'.format(chat_id))


def main(api_key):
    global bot
    bot = telepot.Bot(api_key)
    bot.message_loop(handle)
    print('Listening ...')
    while True:
        time.sleep(10)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        print('Usage: id.py TELEGRAM_API_KEY')
