#!/usr/bin/env python3

"""

    Smart Home Bot for Telegram.

    Copyright (c) 2017 Oliver Lau <oliver@ersatzworld.net>
    All rights reserved.

"""

import json
import telepot
from telepot.delegate import per_chat_id, create_open, pave_event_space
from pprint import pprint


class ChatUser(telepot.helper.ChatHandler):
    def __init__(self, *args, **kwargs):
        super(ChatUser, self).__init__(*args, **kwargs)
        self.timeout_secs = 10
        if 'timeout' in kwargs.keys():
            self.timeout_secs = kwargs['timeout']
        self.verbose = True
        if 'verbose' in kwargs.keys():
            self.verbose = kwargs['verbose']
        self.authorized_users = [217884835]
        if 'authorized_users' in kwargs.keys():
            self.authorized_users = kwargs['authorized_users']

    def open(self, initial_msg, seed):
        self.on_chat_message(initial_msg)
        return True

    def on__idle(self, event):
        self.sender.sendMessage("Session expired. - You can ignore this message.")
        self.close()

    def on_close(self, msg):
        if self.verbose:
            print("on_close() called.")
        return True

    def on_chat_message(self, msg):
        content_type, chat_type, chat_id = telepot.glance(msg)
        if chat_id not in self.authorized_users:
            self.sender.sendMessage("Go f*ck yourself!")
            print("Unauthorized access from {}".format(msg['chat']['id']))
            self.close()
            return

        if content_type == 'text':
            pprint(msg)
            msg_text = msg['text']
            user_name = msg['from']['first_name']
            self.sender.sendMessage('You ({}) said: {}'.format(user_name, msg_text))
        elif content_type == 'sticker':
            self.sender.sendMessage("I'm ignoring all stickers you send me.")
        elif content_type == 'photo':
            self.sender.sendMessage("I can't make use of your images. But I can show you one of me.")
            photo_file = open(u'facepalm-ernie.jpg', 'rb')
            self.sender.sendPhoto(photo_file, caption="That's me. Nice, huh?")
        elif content_type == 'document':
            self.sender.sendMessage("What do you want me to do with files?")
        else:
            self.sender.sendMessage("{} moved to Nirvana ...".format(content_type))


def main():
    telegram_bot_token = None
    with open('smarthomebot-config.json', 'r') as config_file:
        config = json.load(config_file)

    try:
        telegram_bot_token = config['telegram_bot_token']
    except ValueError:
        print("Error: config file doesn't contain a telegram_bot_token")
        return

    timeout_secs = 10
    if 'timeout_secs' in config.keys():
        timeout_secs = config['timeout_secs']

    authorized_users = [217884835]
    if 'authorized_users' in config.keys():
        authorized_users = config['authorized_users']

    verbose = False
    if 'verbose' in config.keys():
        verbose = config['verbose']

    bot = telepot.DelegatorBot(telegram_bot_token, [
      pave_event_space()(per_chat_id(), create_open, ChatUser, timeout=timeout_secs),
    ])
    bot.message_loop(run_forever='Listening ...'.format(timeout_secs))

if __name__ == '__main__':
    main()
