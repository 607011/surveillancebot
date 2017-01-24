#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

    Smart Home Bot for Telegram.

    Copyright (c) 2017 Oliver Lau <oliver@ersatzworld.net>
    All rights reserved.

"""

import sys
import os
import datetime
import json
import time
import telepot
import subprocess
from telepot.delegate import per_chat_id, create_open, pave_event_space
from pprint import pprint
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class UploadDirectoryEventHandler(FileSystemEventHandler):
    def __init__(self, *args, **kwargs):
        super(FileSystemEventHandler, self).__init__()
        self.bot = kwargs["bot"]
        self.verbose = kwargs["verbose"]
        self.image_folder = kwargs["image_folder"]
        self.authorized_users = kwargs["authorized_users"]
        self.path_to_ffmpeg = kwargs["path_to_ffmpeg"]

    def dispatch(self, event):
        if event.event_type == "created" and not event.is_directory:
            filename, ext = os.path.splitext(os.path.basename(event.src_path))
            ext = ext.lower()
            if ext in [".jpg", ".png", ".gif"]:
                self.send_photo(event.src_path)
            elif ext in [".mp4", ".avi", ".mov", ".mpg", ".ts"]:
                self.send_video(event.src_path)


    def send_message(self, msg):
        for user in self.authorized_users:
            pass

    def send_photo(self, photo_filename):
        for user in self.authorized_users:
            if self.verbose:
                print("Sending photo {} ...".format(photo_filename))
            while os.stat(photo_filename).st_size == 0: # make sure file is written
                time.sleep(0.1)
            self.bot.sendPhoto(user, open(photo_filename, "rb"),
                               caption=datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
            os.remove(photo_filename)

    def send_video(self, src_video_filename):
        for user in self.authorized_users:
            if self.verbose:
                print("Sending video {} ...".format(src_video_filename))
            while os.stat(src_video_filename).st_size == 0: # make sure file is written
                time.sleep(0.1)
            filename, ext = os.path.splitext(os.path.basename(src_video_filename))
            dst_video_filename = "{}/{}-converted{}".format(os.path.dirname(src_video_filename), filename, ".mp4")
            subprocess.run(
                [self.path_to_ffmpeg,
                 "-y",
                 "-i",
                 src_video_filename,
                 dst_video_filename],
                shell=False, check=True)
            self.bot.sendVideo(user, open(src_video_filename, "rb"),
                               caption="{} {}".format(filename, datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")))
            os.remove(src_video_filename)
            os.remove(dst_video_filename)


class ChatUser(telepot.helper.ChatHandler):

    AUTHORIZED_USERS = [217884835]

    def __init__(self, *args, **kwargs):
        super(ChatUser, self).__init__(*args, **kwargs)
        self.timeout_secs = 10
        if "timeout" in kwargs.keys():
            self.timeout_secs = kwargs["timeout"]
        self.verbose = True
        if "verbose" in kwargs.keys():
            self.verbose = kwargs["verbose"]
        self.authorized_users = ChatUser.AUTHORIZED_USERS
        if "authorized_users" in kwargs.keys():
            self.authorized_users = kwargs["authorized_users"]

    def open(self, initial_msg, seed):
        self.on_chat_message(initial_msg)
        return True

    def on__idle(self, event):
        self.sender.sendMessage("Session expired. - Keep cool, nothing to worry about.")
        self.close()

    def on_close(self, msg):
        if self.verbose:
            print("on_close() called.")
        return True

    def on_chat_message(self, msg):
        content_type, chat_type, chat_id = telepot.glance(msg)
        if chat_id not in self.authorized_users:
            self.sender.sendMessage("Go away")
            if self.verbose:
                print("Unauthorized access from {}".format(msg["chat"]["id"]))
            self.close()
            return

        if content_type == "text":
            pprint(msg)
            msg_text = msg["text"]
            user_name = msg["from"]["first_name"]
            self.sender.sendMessage('You ({}) said: {}'.format(user_name, msg_text))
        elif content_type == "sticker":
            self.sender.sendMessage("I'm ignoring all stickers you send me.")
        elif content_type == "photo":
            self.sender.sendMessage("I can't make use of your images. But I can show you one of me.")
            photo_file = open("facepalm-ernie.jpg", "rb")
            self.sender.sendPhoto(photo_file,
                                  caption="That's me. Nice, huh?")
        elif content_type == "document":
            self.sender.sendMessage("What do you want me to do with files?")
        else:
            self.sender.sendMessage("{} moved to Nirvana ...".format(content_type))


def main(arg):
    telegram_bot_token = None
    timeout_secs = 10
    image_folder = "/home/ftp-upload"
    authorized_users = ChatUser.AUTHORIZED_USERS
    path_to_ffmpeg = "/Users/ola/Workspace/smarthomebot/ffmpeg"
    verbose = False

    with open("smarthomebot-config.json", "r") as config_file:
        config = json.load(config_file)
    if "telegram_bot_token" in config.keys():
        telegram_bot_token = config["telegram_bot_token"]
    if telegram_bot_token == None:
        print("Error: config file doesn't contain a telegram_bot_token")
        return
    if "image_folder" in config.keys():
        image_folder = config["image_folder"]
    if "timeout_secs" in config.keys():
        timeout_secs = config["timeout_secs"]
    if "authorized_users" in config.keys():
        authorized_users = config["authorized_users"]
    if "path_to_ffmpeg" in config.keys():
        path_to_ffmpeg = config["path_to_ffmpeg"]
    if "verbose" in config.keys():
        verbose = config["verbose"]

    bot = telepot.DelegatorBot(telegram_bot_token, [
      pave_event_space()(per_chat_id(), create_open, ChatUser, timeout=timeout_secs),
    ])

    if verbose:
       print("Monitoring {} ...".format(image_folder))
    event_handler = UploadDirectoryEventHandler(image_folder=image_folder,
                                                verbose=verbose,
                                                authorized_users=authorized_users,
                                                path_to_ffmpeg=path_to_ffmpeg,
                                                bot=bot)
    observer = Observer()
    observer.schedule(event_handler, image_folder, recursive=False)
    observer.start()
    bot.message_loop(run_forever="Bot is listening ...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
    if verbose:
        print("Exiting ...")

if __name__ == "__main__":
    main(sys.argv)
