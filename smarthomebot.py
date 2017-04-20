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
import random
import telepot
import subprocess
import shelve
import urllib3
import pygame
import audiotools
import threading
import queue
from tempfile import mkstemp
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton
from telepot.delegate import per_chat_id_in, create_open, pave_event_space, include_callback_query_chat_id
from pprint import pprint
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.job import Job
from PIL import Image


APPNAME = 'smarthomebot'
APPVERSION = '1.0.2'


class easydict(dict):
    def __missing__(self, key):
        self[key] = easydict()
        return self[key]


class Task(object):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def take_snapshot_thread():

    def get_image_from_url(url, username, password):
        error_msg = None
        response = None
        try:
            http = urllib3.PoolManager()
            headers = urllib3.util.make_headers(basic_auth='{}:{}'
                                                .format(username, password)) if username and password else None
            response = http.request('GET', url, headers=headers)
        except urllib3.exceptions.HTTPError as e:
            error_msg = e.reason
        return response, error_msg

    while True:
        task = snapshot_queue.get()
        if task is None:
            break
        for camera in task.cameras:
            if camera.get('snapshot_url'):
                bot.sendChatAction(task.chat_id, action='upload_photo')
                response, error_msg = \
                    get_image_from_url(camera.get('snapshot_url'),
                                       camera.get('username'),
                                       camera.get('password'))
                if error_msg:
                    bot.sendMessage(task.chat_id,
                                    'Fehler beim Abrufen des Schnappschusses via {}: {}'
                                    .format(camera.get('snapshot_url'), error_msg))
                elif response and response.data:
                    handle, photo_filename = mkstemp(prefix='snapshot-', suffix='.jpg')
                    f = open(photo_filename, 'wb+')
                    f.write(response.data)
                    f.close()
                    bot.sendPhoto(task.chat_id,
                                  open(photo_filename, 'rb'),
                                  caption=datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S'))
                    os.remove(photo_filename)
        snapshot_queue.task_done()
        if hasattr(task, 'callback'):
            task.callback()


def make_snapshot(chat_id):
    snapshot_queue.put(Task(cameras=cameras.values(), chat_id=chat_id))


def process_text_thread():
    while True:
        task = text_queue.get()
        if task is None:
            break
        for encoding in encodings:
            try:
                with open(task.src_filename, 'r', encoding=encoding) as f:
                    msg = f.read()
                    if len(msg) > 2048:
                        msg = msg[0:2047]
                    print(msg)
            except UnicodeDecodeError:
                if verbose:
                    print('Decoding file as {:s} failed, trying another encoding ...'.format(encoding))
            else:
                break
        if msg:
            for user in authorized_users:
                bot.sendMessage(user, msg)
        os.remove(task.src_filename)


def process_document_thread():
    while True:
        task = document_queue.get()
        if task is None:
            break
        for user in authorized_users:
            bot.sendDocument(user, open(task.src_filename, 'rb'),
                             caption=datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S'))
        os.remove(task.src_filename)


def process_video_thread():
    while True:
        task = video_queue.get()
        if task is None:
            break
        for user in authorized_users:
            bot.sendChatAction(user, action='upload_video')
        handle, dst_video_filename = mkstemp(prefix='smarthomebot-', suffix='.mp4')
        cmd = [path_to_ffmpeg,
               '-y',
               '-loglevel', 'panic',
               '-i', task.src_filename,
               '-vf', 'scale=640:-1',
               '-movflags',
               '+faststart',
               '-c:v', 'libx264',
               '-preset', 'fast',
               dst_video_filename]
        if verbose:
            print('Started {}'.format(' '.join(cmd)))
        subprocess.call(cmd, shell=False)
        for user in authorized_users:
            bot.sendVideo(user, open(dst_video_filename, 'rb'),
                          caption='{} ({})'.format(os.path.basename(task.src_filename),
                                                   datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')))
        os.remove(dst_video_filename)
        os.remove(task.src_filename)
        video_queue.task_done()


def process_voice_thread():
    while True:
        task = voice_queue.get()
        if task is None:
            break
        handle, voice_filename = mkstemp(prefix='voice-', suffix='.oga')
        handle, converted_audio_filename = mkstemp(prefix='converted-audio-', suffix='.oga')
        bot.sendChatAction(task.chat_id, action='upload_audio')
        bot.download_file(task.file_id, voice_filename)
        audiotools.open(voice_filename).convert(converted_audio_filename, audiotools.VorbisAudio)
        pygame.mixer.music.load(converted_audio_filename)
        pygame.mixer.music.play()
        os.remove(converted_audio_filename)
        os.remove(voice_filename)
        bot.sendMessage(task.chat_id, 'Sprachnachricht wurde abgespielt.')
        voice_queue.task_done()


def process_photo_thread():
    while True:
        task = photo_queue.get()
        if task is None:
            break
        dst_photo_filename = task.src_filename
        if type(max_photo_size) is int:
            im = Image.open(task.src_filename)
            if im.width > max_photo_size or im.height > max_photo_size:
                im.thumbnail((max_photo_size, max_photo_size), Image.BILINEAR)
                handle, dst_photo_filename = mkstemp(prefix='smarthomebot-', suffix='.jpg')
                if verbose:
                    print('Resizing photo to {} ...'.format(dst_photo_filename))
                im.save(dst_photo_filename, format='JPEG', quality=87)
                os.remove(task.src_filename)
            im.close()
        if verbose:
            print('Sending photo {} ...'.format(dst_photo_filename))
        for user in authorized_users:
            bot.sendPhoto(user, open(dst_photo_filename, 'rb'),
                          caption=datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S'))
        os.remove(dst_photo_filename)


class UploadDirectoryEventHandler(FileSystemEventHandler):

    def __init__(self, *args, **kwargs):
        super(UploadDirectoryEventHandler, self).__init__()

    def on_created(self, event):
        if not event.is_directory:
            filename, ext = os.path.splitext(os.path.basename(event.src_path))
            ext = ext.lower()
            if ext in ['.jpg', '.png']:
                self.process_photo(event.src_path)
            elif ext in ['.txt']:
                self.process_text(event.src_path)
            elif ext in ['.avi', '.mp4', '.mkv', '.m4v', '.mov', '.mpg']:
                self.process_video(event.src_path)
            else:
                self.process_document(event.src_path)

    def process_text(self, src_text_filename):
        while os.stat(src_text_filename).st_size == 0:  # make sure file is written
            time.sleep(0.1)
        if verbose:
            print('New text file detected: {}'.format(src_text_filename))
        if alerting_on and do_send_text:
            text_queue.put(Task(src_filename=src_text_filename))
        else:
            os.remove(src_text_filename)

    def process_document(self, src_document_filename):
        while os.stat(src_document_filename).st_size == 0:  # make sure file is written
            time.sleep(0.1)
        print('New document detected: {}'.format(src_document_filename))
        if alerting_on and do_send_documents:
            document_queue.put(Task(src_filename=src_document_filename))
        else:
            os.remove(src_document_filename)

    def process_photo(self, src_photo_filename):
        while os.stat(src_photo_filename).st_size == 0:  # make sure file is written
            time.sleep(0.1)
        if verbose:
            print('New photo file detected: {}'.format(src_photo_filename))
        if alerting_on and do_send_photos:
            photo_queue.put(Task(src_filename=src_photo_filename))
        else:
            os.remove(src_photo_filename)

    def process_video(self, src_video_filename):
        while os.stat(src_video_filename).st_size == 0:  # make sure file is written
            time.sleep(0.1)
        if verbose:
            print('New video file detected: {}'.format(src_video_filename))
        if alerting_on and do_send_videos and type(path_to_ffmpeg) is str:
            video_queue.put(Task(src_filename=src_video_filename))
        else:
            os.remove(src_video_filename)


class ChatUser(telepot.helper.ChatHandler):

    IdleMessages = ['tüdelü …', '*gähn*', 'Mir ist langweilig.', 'Chill dein Life! Alles cool hier.',
                    'Hier ist tote Hose.', 'Nix los hier …', 'Scheint niemand zu Hause zu sein.',
                    'Sanft ruht der See.', 'Hallo-o!!!', 'Alles cool, Digga.', 'Ich kuck und kuck, aber nix passiert.',
                    'Das Adlerauge ist wachsam, sieht aber nüscht.', 'Nix tut sich.',
                    'Mach du dein Ding. Ich mach hier meins.', 'Alles voll secure in da house.']

    def __init__(self, *args, **kwargs):
        super(ChatUser, self).__init__(*args, **kwargs)
        self.snapshot_job = None

    def open(self, initial_msg, seed):
        content_type, chat_type, chat_id = telepot.glance(initial_msg)
        self.init_scheduler(chat_id)

    def init_scheduler(self, chat_id):
        global settings, scheduler
        interval = settings[chat_id]['snapshot']['interval']
        if type(interval) is not int:
            interval = 0
            settings[chat_id]['snapshot']['interval'] = interval
        if interval > 0:
            if type(self.snapshot_job) is Job:
                self.snapshot_job.remove()
                self.snapshot_job = scheduler.add_job(
                    make_snapshot, 'interval',
                    seconds=interval,
                    kwargs={'chat_id': chat_id})
        else:
            if type(self.snapshot_job) is Job:
                self.snapshot_job.remove()

    def on__idle(self, event):
        if alerting_on:
            ridx = random.randint(0, len(ChatUser.IdleMessages) - 1)
            self.sender.sendMessage(ChatUser.IdleMessages[ridx], parse_mode='Markdown')

    def on_close(self, msg):
        if verbose:
            print('on_close() called. {}'.format(msg))
        if type(self.snapshot_job) is Job:
            self.snapshot_job.remove()
        return True

    def send_snapshot_menu(self):
        kbd = [ InlineKeyboardButton(text=cameras[c]['name'], callback_data=c)
                for c in cameras.keys() ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[kbd])
        self.sender.sendMessage('Schnappschuss anzeigen von:', reply_markup=keyboard)

    def send_main_menu(self):
        global alerting_on
        kbd = [
            InlineKeyboardButton(text=chr(0x1F4F7) + 'Schnappschuss',
                                 callback_data='snapshot'),
            InlineKeyboardButton(text=[chr(0x25B6) + chr(0xFE0F) + 'Alarme ein',
                                       chr(0x23F9) + 'Alarme aus'][alerting_on],
                                 callback_data=['enable', 'disable'][alerting_on])
            ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[kbd])
        self.sender.sendMessage('Wähle eine Aktion:', reply_markup=keyboard)

    def on_callback_query(self, msg):
        global alerting_on, snapshooter, snapshot_queue
        query_id, from_id, query_data = telepot.glance(msg, flavor='callback_query')
        print('Callback Query:', query_id, from_id, query_data)
        if cameras.get(query_data):
            bot.answerCallbackQuery(query_id,
                                    text='Schnappschuss von deiner Kamera "{}"'.format(query_data))
            snapshot_queue.put(Task(cameras=[cameras[query_data]],
                                    chat_id=from_id,
                                    callback=lambda: self.send_snapshot_menu()))
        elif query_data == 'disable':
            alerting_on = False
            self.bot.answerCallbackQuery(query_id, text='Alarme wurden ausgeschaltet.')
            self.send_main_menu()
        elif query_data == 'enable':
            alerting_on = True
            self.bot.answerCallbackQuery(query_id, text='Alarme wurden eingeschaltet.')
            self.send_main_menu()
        elif query_data == 'snapshot':
            self.bot.answerCallbackQuery(query_id)
            self.send_snapshot_menu()

    def on_chat_message(self, msg):
        global scheduler, settings, alerting_on
        content_type, chat_type, chat_id = telepot.glance(msg)
        if content_type == 'text':
            if verbose:
                pprint(msg)
            msg_text = msg['text']
            if msg_text.startswith('/start'):
                self.sender.sendMessage('*Hallo, ich bin dein Heimüberwachungs-Bot* v' + APPVERSION +
                                        chr(0x1F916) + "\n\n"
                                        'Ich benachrichtige dich, wenn deine Webcams Bewegungen '
                                        'und laute Geräusche erkannt haben '
                                        'und sende dir ein Video von dem Vorfall.' + "\n",
                                        parse_mode='Markdown')
                self.send_main_menu()
            elif msg_text.startswith('/snapshot'):
                c = msg_text.split()[1:]
                subcmd = c[0].lower() if len(c) > 0 else None
                if subcmd is None:
                    self.send_snapshot_menu()
                else:
                    if subcmd == 'interval':
                        if len(c) > 1:
                            interval = int(c[1])
                            settings[chat_id]['snapshot']['interval'] = interval
                            if interval > 0:
                                if type(self.snapshot_job) is Job:
                                    self.snapshot_job.remove()
                                self.snapshot_job = scheduler.add_job(make_snapshot, 'interval',
                                                                      seconds=interval,
                                                                      kwargs={'chat_id': chat_id})
                                self.sender.sendMessage('Schnappschüsse sind aktiviert. '
                                                        'Das Intervall ist auf {} Sekunden eingestellt.'
                                                        .format(interval))
                            else:
                                if type(self.snapshot_job) is Job:
                                    self.snapshot_job.remove()
                                    self.sender.sendMessage('Zeitgesteuerte Schnappschüsse sind nun deaktiviert.')
                                else:
                                    self.sender.sendMessage('Es waren keine zeitgesteuerten Schnappschüsse aktiviert.')
                        else:
                            if type(settings[chat_id]['snapshot']['interval']) is not int:
                                self.sender.sendMessage('Schnappschussintervall wurde noch nicht eingestellt.')
                            elif settings[chat_id]['snapshot']['interval'] < 1:
                                self.sender.sendMessage('Aufnehmen von Schnappschüssen in Intervallen '
                                                        'ist derzeit deaktiviert.')
                            else:
                                self.sender.sendMessage('Schnappschussintervall ist derzeit auf '
                                                        '{} Sekunden eingestellt.'
                                                        .format(settings[chat_id]['snapshot']['interval']))
            elif msg_text.startswith('/enable') or \
                    any(cmd in msg_text.lower() for cmd in ['on', 'go', '1', 'ein']):
                alerting_on = True
                self.sender.sendMessage('Alarme ein.')
            elif msg_text.startswith('/disable') or \
                    any(cmd in msg_text.lower() for cmd in ['off', 'stop', '0', 'aus']):
                alerting_on = False
                self.sender.sendMessage('Alarme aus.')
            elif msg_text.startswith('/toggle'):
                alerting_on = not alerting_on
                self.sender.sendMessage('Alarme sind nun {}geschaltet.'.format(['aus', 'ein'][alerting_on]))

            elif msg_text.startswith('/help'):
                self.sender.sendMessage("Verfügbare Kommandos:\n\n"
                                        "/help diese Nachricht anzeigen\n"
                                        "/enable /disable /toggle Benachrichtigungen aktivieren/deaktivieren\n"
                                        "/snapshot Liste der Kameras anzeigen, die Schnappschüsse liefern können\n"
                                        "/snapshot `interval` Das Zeitintervall (Sek.) anzeigen, in dem "
                                        "Schnappschüsse von den Kameras abgerufen und angezeigt werden sollen\n"
                                        "/snapshot `interval` `secs` Schnappschussintervall auf `secs` Sekunden "
                                        "setzen (`0` für aus)\n"
                                        "/start den Bot (neu)starten\n",
                                        parse_mode='Markdown')
            elif msg_text.startswith('/'):
                self.sender.sendMessage('Unbekanntes Kommando. /help für weitere Infos eintippen.')
            else:
                self.sender.sendMessage('Ich bin nicht sehr gesprächig. Tippe /help für weitere Infos ein.')
        elif content_type == 'voice':
            if audio_on:
                voice_queue.put(Task(file_id=msg['voice']['file_id'],
                                     chat_id=chat_id))
            else:
                self.sender.sendMessage('Sprachausgabe ist vorläufig deaktiviert.')
        else:
            self.sender.sendMessage('Dein "{}" ist im Nirwana gelandet ...'.format(content_type))


settings = easydict()
scheduler = BackgroundScheduler()
snapshot_queue = queue.Queue()
text_queue = queue.Queue()
document_queue = queue.Queue()
video_queue = queue.Queue()
voice_queue = queue.Queue()
photo_queue = queue.Queue()
snapshooter = None
text_processor = None
document_processor = None
video_processor = None
voice_processor = None
photo_processor = None
authorized_users = None
cameras = None
verbose = None
path_to_ffmpeg = None
max_photo_size = None
bot = None
alerting_on = True
audio_on = None
do_send_videos = None
do_send_photos = None
do_send_text = None
do_send_documents = None
encodings = ['utf-8', 'latin1', 'macroman', 'windows-1252', 'windows-1250']


def main():
    global bot, authorized_users, cameras, verbose, settings, scheduler, \
        encodings, path_to_ffmpeg, audio_on, max_photo_size, \
        do_send_text, do_send_documents, do_send_videos, do_send_photos, \
        snapshooter, photo_processor, video_processor, voice_processor
    config_filename = 'smarthomebot-config.json'
    shelf = shelve.open('.smarthomebot.shelf')
    if APPNAME in shelf.keys():
        settings = easydict(shelf[APPNAME])
    try:
        with open(config_filename, 'r') as config_file:
            config = json.load(config_file)
    except FileNotFoundError as e:
        print('Error: config file not found: {}'.format(e))
        return
    except ValueError as e:
        print('Error: invalid config file "{}": {}'.format(config_filename, e))
        return
    telegram_bot_token = config.get('telegram_bot_token')
    if not telegram_bot_token:
        print('Error: config file doesn\'t contain a `telegram_bot_token`')
        return
    authorized_users = config.get('authorized_users')
    if type(authorized_users) is not list or len(authorized_users) == 0:
        print('Error: config file doesn\'t contain an `authorized_users` list')
        return
    cameras = config.get('cameras', [])
    if type(cameras) is not dict:
        print('Error: config file doesn\'t define any `cameras`')
        return
    timeout_secs = config.get('timeout_secs', 10*60)
    image_folder = config.get('image_folder', '/home/ftp-upload')
    path_to_ffmpeg = config.get('path_to_ffmpeg')
    max_photo_size = config.get('max_photo_size', 1280)
    verbose = config.get('verbose', False)
    do_send_photos = config.get('send_photos', False)
    do_send_videos = config.get('send_videos', True)
    do_send_text = config.get('send_text', False)
    do_send_documents = config.get('send_documents', False)
    audio_on = config.get('audio', {}).get('enabled', False)
    if audio_on:
        pygame.mixer.pre_init(frequency=48000, size=-16, channels=2, buffer=4096)
        pygame.mixer.init()
    bot = telepot.DelegatorBot(telegram_bot_token, [
        include_callback_query_chat_id(pave_event_space())(per_chat_id_in(authorized_users, types='private'),
                                                           create_open,
                                                           ChatUser,
                                                           timeout=timeout_secs)
    ])
    snapshooter = threading.Thread(target=take_snapshot_thread)
    snapshooter.start()
    if do_send_text:
        text_processor = threading.Thread(target=process_text_thread)
        text_processor.start()
        if verbose:
            print('Enabled text processing.')
    if do_send_documents:
        document_processor = threading.Thread(target=process_document_thread)
        document_processor.start()
        if verbose:
            print('Enabled document processing.')
    if do_send_photos:
        photo_processor = threading.Thread(target=process_photo_thread)
        photo_processor.start()
        if verbose:
            print('Enabled photo processing.')
    if do_send_videos:
        video_processor = threading.Thread(target=process_video_thread)
        video_processor.start()
        if verbose:
            print('Enabled video processing.')
    if audio_on:
        voice_processor = threading.Thread(target=process_voice_thread)
        voice_processor.start()
        if verbose:
            print('Enabled audio processing.')
    if verbose:
        print('Monitoring {} ...'.format(image_folder))
    scheduler.start()
    event_handler = UploadDirectoryEventHandler(ignore_directories=True)
    observer = Observer()
    observer.schedule(event_handler, image_folder, recursive=True)
    observer.start()
    try:
        bot.message_loop(run_forever='Bot listening ...')
    except KeyboardInterrupt:
        pass
    if verbose:
        print('Exiting ...')
    observer.stop()
    observer.join()
    shelf[APPNAME] = settings
    shelf.sync()
    shelf.close()
    scheduler.shutdown()

    snapshot_queue.put(None)
    snapshooter.join()
    if do_send_videos:
        video_queue.put(None)
        video_processor.join()
    if do_send_photos:
        photo_queue.put(None)
        photo_processor.join()
    if do_send_text:
        text_queue.put(None)
        text_processor.join()
    if do_send_documents:
        document_queue.put(None)
        document_processor.join()
    if audio_on:
        voice_queue.put(None)
        voice_processor.join()

if __name__ == '__main__':
    main()
