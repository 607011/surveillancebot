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
import urllib.request
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton
from telepot.delegate import per_chat_id, create_open, pave_event_space, include_callback_query_chat_id
from pprint import pprint
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from PIL import Image
from tempfile import mkstemp


class UploadDirectoryEventHandler(FileSystemEventHandler):

    def __init__(self, *args, **kwargs):
        super(FileSystemEventHandler, self).__init__()
        self.bot = kwargs["bot"]
        self.verbose = kwargs["verbose"]
        self.image_folder = kwargs["image_folder"]
        self.authorized_users = kwargs["authorized_users"]
        self.path_to_ffmpeg = kwargs["path_to_ffmpeg"]
        self.max_photo_size = kwargs["max_photo_size"]

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

    def send_photo(self, src_photo_filename):
        while os.stat(src_photo_filename).st_size == 0:  # make sure file is written
            time.sleep(0.1)
        dst_photo_filename = src_photo_filename
        if self.max_photo_size:
            im = Image.open(src_photo_filename)
            if im.width > self.max_photo_size or im.height > self.max_photo_size:
                im.thumbnail((self.max_photo_size, self.max_photo_size), Image.BILINEAR)
                handle, dst_photo_filename = mkstemp(prefix="smarthomebot-", suffix=".jpg")
                if self.verbose:
                    print("resizing photo to {} ...".format(dst_photo_filename))
                im.save(dst_photo_filename, format="JPEG", quality=87)
                os.remove(src_photo_filename)
            im.close()
        for user in self.authorized_users:
            if self.verbose:
                print("Sending photo {} ...".format(dst_photo_filename))
            self.bot.sendPhoto(user, open(dst_photo_filename, "rb"),
                               caption=datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        os.remove(dst_photo_filename)

    def send_video(self, src_video_filename):
        if self.path_to_ffmpeg is None:
            if self.verbose:
                print("No path to ffmpeg given. Cannot send videos.")
            return
        for user in self.authorized_users:
            while os.stat(src_video_filename).st_size == 0: # make sure file is written
                time.sleep(0.1)
            handle, dst_video_filename = mkstemp(prefix="smarthomebot-", suffix=".mp4")
            if self.verbose:
                print("Converting video {} to {} ...".format(src_video_filename, dst_video_filename))
            subprocess.run(
                [self.path_to_ffmpeg,
                 "-y",
                 "-loglevel",
                 "panic",
                 "-i",
                 src_video_filename,
                 "-vf",
                 "scale=480:320",
                 "-movflags",
                 "+faststart",
                 "-c:v",
                 "libx264",
                 "-preset",
                 "fast",
                 dst_video_filename],
                shell=False, check=True)
            self.bot.sendVideo(user, open(dst_video_filename, "rb"),
                               caption="{} {}".format(os.path.basename(src_video_filename),
                                                      datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")))
            os.remove(src_video_filename)
            os.remove(dst_video_filename)


class ChatUser(telepot.helper.ChatHandler):

    def __init__(self, *args, **kwargs):
        global authorized_users, verbose

        super(ChatUser, self).__init__(*args, **kwargs)
        self.timeout_secs = 10
        if "timeout" in kwargs.keys():
            self.timeout_secs = kwargs["timeout"]
        self.verbose = verbose
        self.authorized_users = authorized_users

    def open(self, initial_msg, seed):
        self.on_chat_message(initial_msg)
        return True

    def on__idle(self, event):
        self.sender.sendMessage("*yawn*")
        self.close()

    def on_close(self, msg):
        if self.verbose:
            print("on_close() called.")
        return True

    def on_callback_query(self, msg):
        global cameras
        query_id, from_id, query_data = telepot.glance(msg, flavor="callback_query")
        print("Callback Query:", query_id, from_id, query_data)
        self.bot.answerCallbackQuery(query_id, text="Showing you a snapshot camera ‘{}‘".format(query_data))
        if query_data in cameras.keys():
            handle, photo_filename = mkstemp(prefix="snapshot-", suffix=".jpg")
            response = None
            try:
                response = urllib.request.urlopen(cameras[query_data]["snapshot_url"])
            except urllib.error.URLError:
                pass
            if response is None:
                return
            f = open(photo_filename, 'wb+')
            f.write(response.read())
            f.close()
            self.sender.sendPhoto(open(photo_filename, 'rb'), caption=datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
            os.remove(photo_filename)

    def on_chat_message(self, msg):
        global cameras

        content_type, chat_type, chat_id = telepot.glance(msg)
        if chat_id not in self.authorized_users:
            self.sender.sendMessage("Go away!")
            if self.verbose:
                print("Unauthorized access from {}".format(msg["chat"]["id"]))
            self.close()
            return

        if content_type == "text":
            if self.verbose:
                pprint(msg)
            self.sender.sendMessage('You ({}) said: {}'.format(msg["from"]["first_name"], msg["text"]))
            if msg["text"] == "/snapshot":
                kbd = [InlineKeyboardButton(text=cameras[c]["name"], callback_data=c) for c in cameras.keys()]
                keyboard = InlineKeyboardMarkup(inline_keyboard=[kbd])
                self.sender.sendMessage("Choose camera to take a snapshot from:", reply_markup=keyboard)
        elif content_type == "sticker":
            self.sender.sendMessage("I'm ignoring all stickers you send me.")
        elif content_type == "photo":
            self.sender.sendMessage("I can't make use of your images. But I can show you one of me.")
            photo_file = open("facepalm-ernie.jpg", "rb")
            self.sender.sendPhoto(photo_file, caption="That's me. Nice, huh?")
        elif content_type == "document":
            self.sender.sendMessage("What do you want me to do with files?")
        else:
            self.sender.sendMessage("{} moved to Nirvana ...".format(content_type))


# global variables needed for ChatHandler (which unfortunately doesn't allow extra **kwargs)
authorized_users = None
cameras = None
path_to_ffmpeg = None
verbose = False


def main(arg):
    global authorized_users, cameras, path_to_ffmpeg, verbose
    timeout_secs = 10 * 60
    image_folder = "/home/ftp-upload"
    max_photo_size = 1280
    telegram_bot_token = None
    config_filename = "smarthomebot-config.json"

    with open(config_filename, "r") as config_file:
        config = json.load(config_file)
    if "telegram_bot_token" in config.keys():
        telegram_bot_token = config["telegram_bot_token"]
    if not telegram_bot_token:
        print("Error: config file doesn't contain a telegram_bot_token")
        return
    if "authorized_users" in config.keys():
        authorized_users = config["authorized_users"]
    if type(authorized_users) is not list or len(authorized_users) == 0:
        print("Error: config file doesn't contain an authorized_users list")
        return
    if "timeout_secs" in config.keys():
        timeout_secs = config["timeout_secs"]
    if "cameras" in config.keys():
        cameras = config["cameras"]
    if "image_folder" in config.keys():
        image_folder = config["image_folder"]
    if "path_to_ffmpeg" in config.keys():
        path_to_ffmpeg = config["path_to_ffmpeg"]
    if "max_photo_size" in config.keys():
        max_photo_size = config["max_photo_size"]
    if "verbose" in config.keys():
        verbose = config["verbose"]

    bot = telepot.DelegatorBot(telegram_bot_token, [
        include_callback_query_chat_id(pave_event_space())(per_chat_id(), create_open, ChatUser, timeout=timeout_secs),
    ])

    if verbose:
       print("Monitoring {} ...".format(image_folder))
    event_handler = UploadDirectoryEventHandler(
        image_folder=image_folder,
        verbose=verbose,
        authorized_users=authorized_users,
        path_to_ffmpeg=path_to_ffmpeg,
        max_photo_size=max_photo_size,
        bot=bot)
    observer = Observer()
    observer.schedule(event_handler, image_folder, recursive=False)
    observer.start()

    bot.message_loop(run_forever='Listening ...')

    if verbose:
        print("Exiting ...")
    observer.stop()
    observer.join()

if __name__ == "__main__":
    main(sys.argv)
