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
import shelve
import urllib.request
from tempfile import mkstemp
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton
from telepot.delegate import per_chat_id, create_open, pave_event_space, include_callback_query_chat_id
from pprint import pprint
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.job import Job
from PIL import Image


APPNAME = "smarthomebot"


class easydict(dict):
    def __missing__(self, key):
        self[key] = easydict()
        return self[key]


def make_snapshot(urls, bot, chat_id):
    for url in urls:
        handle, photo_filename = mkstemp(prefix="snapshot-", suffix=".jpg")
        response = None
        try:
            response = urllib.request.urlopen(url)
        except urllib.error.URLError as e:
            bot.sendMessage(chat_id, "Error accessing snapshot URL {}: {}".format(url, e.reason))
        if response is None:
            return
        f = open(photo_filename, "wb+")
        f.write(response.read())
        f.close()
        bot.sendPhoto(chat_id, open(photo_filename, "rb"), caption=datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        os.remove(photo_filename)


class UploadDirectoryEventHandler(FileSystemEventHandler):

    def __init__(self, *args, **kwargs):
        super(FileSystemEventHandler, self).__init__()
        self.bot = kwargs["bot"]
        self.verbose = kwargs["verbose"]
        self.image_folder = kwargs["image_folder"]
        self.authorized_users = kwargs["authorized_users"] or []
        self.path_to_ffmpeg = kwargs["path_to_ffmpeg"]
        self.max_photo_size = kwargs["max_photo_size"]

    def dispatch(self, event):
        if event.event_type == "created" and not event.is_directory:
            filename, ext = os.path.splitext(os.path.basename(event.src_path))
            ext = ext.lower()
            if ext in [".jpg", ".png"]:
                self.send_photo(event.src_path)
            elif ext in [".avi", ".mp4", ".mkv", ".m4v", ".mov", ".mpg"]:
                self.send_video(event.src_path)

    def send_photo(self, src_photo_filename):
        while os.stat(src_photo_filename).st_size == 0:  # make sure file is written
            time.sleep(0.1)
        if self.verbose:
            print("New photo file detected: {}".format(src_photo_filename))
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
        """
        for user in self.authorized_users:
            if self.verbose:
                print("Sending photo {} ...".format(dst_photo_filename))
            self.bot.sendPhoto(user, open(dst_photo_filename, "rb"),
                               caption=datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        """
        os.remove(dst_photo_filename)

    def send_video(self, src_video_filename):
        global alerting_on
        while os.stat(src_video_filename).st_size == 0:  # make sure file is written
            time.sleep(0.1)
        if self.verbose:
            print("New video file detected: {}".format(src_video_filename))
        if alerting_on and self.path_to_ffmpeg:
            handle, dst_video_filename = mkstemp(prefix="smarthomebot-", suffix=".mp4")
            if self.verbose:
                print("Converting video {} to {} ...".format(src_video_filename, dst_video_filename))
            subprocess.call(
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
                shell=False)
            for user in self.authorized_users:
                self.bot.sendVideo(user, open(dst_video_filename, "rb"),
                                   caption="{} ({})".format(os.path.basename(src_video_filename),
                                                            datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")))
            os.remove(dst_video_filename)
        os.remove(src_video_filename)


class ChatUser(telepot.helper.ChatHandler):
    def __init__(self, *args, **kwargs):
        # these globals are bad, but `ChatHandler` doesn't accept any extra **kwargs than `timeout`
        global authorized_users, cameras, verbose

        super(ChatUser, self).__init__(*args, **kwargs)
        self.timeout_secs = 10
        if "timeout" in kwargs.keys():
            self.timeout_secs = kwargs["timeout"]
        self.verbose = verbose
        self.authorized_users = authorized_users
        self.cameras = cameras

    def open(self, initial_msg, seed):
        global settings, scheduler, job
        content_type, chat_type, chat_id = telepot.glance(initial_msg)
        self.on_chat_message(initial_msg)
        if chat_id not in self.authorized_users:
            print("Unauthoried chat start from {}".format(chat_id))
            self.close()
            return
        interval = settings[chat_id]["snapshot"]["interval"]
        if type(interval) == easydict:
            interval = 0
        if interval > 0:
            if type(job) is Job:
                job.remove()
            job = scheduler.add_job(make_snapshot, 'interval', seconds=interval, kwargs={"bot": self.bot, "chat_id": chat_id, "urls": [cameras[c]["snapshot_url"] for c in self.cameras.keys()]})
            scheduler.resume()
        return True

    def on__idle(self, event):
        self.sender.sendMessage("*yawn*")
        self.close()

    def on_close(self, msg):
        if self.verbose:
            print("on_close() called.")
        return True

    def on_callback_query(self, msg):
        query_id, from_id, query_data = telepot.glance(msg, flavor="callback_query")
        if from_id not in self.authorized_users:
            print("Unauthorized callback from {}".format(from_id))
            self.close()
            return
        # TODO: evaluate callback id
        print("Callback Query:", query_id, from_id, query_data)
        self.bot.answerCallbackQuery(query_id, text="Showing you a snapshot camera ‘{}‘".format(query_data))
        if query_data in self.cameras.keys():
            url = cameras[query_data]["snapshot_url"]
            make_snapshot([url], self.bot, from_id)
            self.send_snapshot_menu()

    def send_snapshot_menu(self):
        kbd = [InlineKeyboardButton(text=self.cameras[c]["name"], callback_data=c) for c in self.cameras.keys()]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[kbd])
        self.sender.sendMessage("Choose camera to take a snapshot from:", reply_markup=keyboard)

    def on_chat_message(self, msg):
        global scheduler, job, settings, alerting_on
        content_type, chat_type, chat_id = telepot.glance(msg)
        if chat_id not in self.authorized_users:
            self.sender.sendMessage("Go away!")
            print("Unauthorized access from {}".format(msg["chat"]["id"]))
            self.close()
            return

        if content_type == "text":
            if self.verbose:
                pprint(msg)
            msg_text = msg["text"]
            if msg_text.startswith("/start"):
                self.sender.sendMessage("*Welcome to your Home Surveillance Bot!*\n\n"
                                        "I'm intended to inform you about possible intruders "
                                        "by sending you snapshots and videos from your cameras as soon as they "
                                        "detect motion or sound in your home.\n",
                                        parse_mode="Markdown")
                self.send_snapshot_menu()
            elif msg_text.startswith("/enable"):
                alerting_on = True
                self.sender.sendMessage("Alerting enabled.")
            elif msg_text.startswith("/disable"):
                alerting_on = False
                self.sender.sendMessage("Alerting disabled.")
            elif msg_text.startswith("/toggle"):
                alerting_on = not alerting_on
                self.sender.sendMessage("Alerting now {}.".format(["disabled", "enabled"][alerting_on]))
            elif msg_text.startswith("/snapshot"):
                c = msg_text.split()[1:]
                if len(c) == 0:
                    self.send_snapshot_menu()
                else:
                    if c[0] == "interval":
                        if len(c) > 1:
                            interval = int(c[1])
                            settings[chat_id]["snapshot"]["interval"] = interval
                            if interval > 0:
                                scheduler.resume()
                                if type(job) is Job:
                                    job.remove()
                                job = scheduler.add_job(make_snapshot, 'interval', seconds=interval, kwargs={"bot": self.bot, "chat_id": chat_id, "urls": [cameras[c]["snapshot_url"] for c in self.cameras.keys()]})
                                self.sender.sendMessage("Snapshot interval set to {} seconds".format(interval))
                            else:
                                scheduler.pause()
                                self.sender.sendMessage("Timed snapshots deactivated")
                        else:
                            if settings[chat_id]["snapshot"]["interval"] == {}:
                                self.sender.sendMessage("Snapshot interval hasn't been set yet.")
                            else:
                                self.sender.sendMessage("Snapshot interval currently set to {} seconds.".format(settings[chat_id]["snapshot"]["interval"]))

            elif msg_text.startswith("/help"):
                self.sender.sendMessage("Available commands:\n\n"
                                        "/help show this message\n"
                                        "/enable /disable /toggle surveillance and alerting\n"
                                        "/snapshot show the list of your cameras to take a snapshot from\n"
                                        "/snapshot `interval` display snapshot interval (secs)\n"
                                        "/snapshot `interval` `secs` set snapshot interval to `secs` (`0` = off)\n"
                                        "/start (re)start this bot\n",
                                        parse_mode="Markdown")
            elif msg_text.startswith("/"):
                self.sender.sendMessage("Unknown command. Enter /help for more info.")
            else:
                self.sender.sendMessage("I'm not very talkative. Try typing /help for more info.")
        else:
            self.sender.sendMessage("Your {} was moved to Nirvana ...".format(content_type))


# global variables needed for ChatHandler (which unfortunately doesn't allow extra **kwargs)
authorized_users = None
cameras = None
verbose = False
settings = easydict()
scheduler = BackgroundScheduler()
job = None
bot = None
alerting_on = True


def main(arg):
    global bot, authorized_users, cameras, verbose, settings, scheduler, job
    path_to_ffmpeg = None
    timeout_secs = 10 * 60
    image_folder = "/home/ftp-upload"
    max_photo_size = 1280
    telegram_bot_token = None
    config_filename = "smarthomebot-config.json"
    shelf = shelve.open(".smarthomebot.shelf")
    if APPNAME in shelf.keys():
        settings = easydict(shelf[APPNAME])

    try:
        with open(config_filename, "r") as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        print("Error: config file '{}' not found: {}".format(config_filename))
        return
    except json.decoder.JSONDecodeError as e:
        print("Error: invalid config file '{}': {} in line {} column {} (position {})".format(config_filename, e.msg, e.lineno, e.colno, e.pos))
        return

    if "telegram_bot_token" in config.keys():
        telegram_bot_token = config["telegram_bot_token"]
    if not telegram_bot_token:
        print("Error: config file doesn't contain a `telegram_bot_token`")
        return
    if "authorized_users" in config.keys():
        authorized_users = config["authorized_users"]
    if type(authorized_users) is not list or len(authorized_users) == 0:
        print("Error: config file doesn't contain an `authorized_users` list")
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
       for user_id in authorized_users:
           bot.sendMessage(user_id, "Bot started.")
    scheduler.start(paused=True)
    event_handler = UploadDirectoryEventHandler(
        image_folder=image_folder,
        verbose=verbose,
        authorized_users=authorized_users,
        path_to_ffmpeg=path_to_ffmpeg,
        max_photo_size=max_photo_size,
        bot=bot)
    observer = Observer()
    observer.schedule(event_handler, image_folder, recursive=True)
    observer.start()
    try:
        bot.message_loop(run_forever='Bot listening ...')
    except KeyboardInterrupt:
        pass
    if verbose:
        print("Exiting ...")
        for user_id in authorized_users:
            bot.sendMessage(user_id, "Bot shut down.")
    observer.stop()
    observer.join()
    shelf[APPNAME] = settings
    shelf.sync()
    shelf.close()
    scheduler.shutdown()


if __name__ == "__main__":
    main(sys.argv)
