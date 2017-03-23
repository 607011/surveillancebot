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
APPVERSION = '1.0'


class easydict(dict):
    def __missing__(self, key):
        self[key] = easydict()
        return self[key]


class Snapshooter(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        global snapshot_queue
        while True:
            task = snapshot_queue.get()
            if verbose:
                print('Snapshooter received', task)
            if task is None:
                break
            for camera in task['cameras']:
                if camera.get('snapshot_url'):
                    task['bot'].sendChatAction(task['chat_id'], action='upload_photo')
                    response, error_msg = \
                        Snapshooter.get_image_from_url(camera.get('snapshot_url'),
                                                       camera.get('username'),
                                                       camera.get('password'))
                    if error_msg:
                        task['bot'].sendMessage(task['chat_id'],
                                               'Fehler beim Abrufen des Schnappschusses via {}: {}'
                                               .format(camera.get('snapshot_url'), error_msg))
                    elif response and response.data:
                        handle, photo_filename = mkstemp(prefix='snapshot-', suffix='.jpg')
                        f = open(photo_filename, 'wb+')
                        f.write(response.data)
                        f.close()
                        task['bot'].sendPhoto(task['chat_id'],
                                              open(photo_filename, 'rb'),
                                              caption=datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S'))
                        os.remove(photo_filename)
            if 'callback' in task.keys():
                task['callback']()
            snapshot_queue.task_done()

    @staticmethod
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


class VideoProcessor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        global verbose, snapshot_queue, path_to_ffmpeg, bot, authorized_users
        while True:
            task = video_queue.get()
            if verbose:
                print('VideoProcessor received', task)
            if task is None:
                break
            for user in authorized_users:
                bot.sendChatAction(user, action='upload_video')
            handle, dst_video_filename = mkstemp(prefix='smarthomebot-', suffix='.mp4')
            cmd = [path_to_ffmpeg,
                   '-y',
                   '-loglevel', 'panic',
                   '-i', task['src_filename'],
                   '-vf', 'scale=640:-1',
                   '-movflags',
                   '+faststart',
                   '-c:v', 'libx264',
                   '-preset', 'fast',
                   dst_video_filename]
            if verbose:
                print('Running ' + ' '.join(cmd))
            rc = subprocess.call(cmd, shell=False)
            for user in authorized_users:
                bot.sendVideo(user, open(dst_video_filename, 'rb'),
                              caption='{} ({})'.format(os.path.basename(task['src_filename']),
                                                       datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')))
            os.remove(dst_video_filename)
            os.remove(task['src_filename'])
            video_queue.task_done()


class VoiceProcessor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        global verbose, voice_queue, bot
        while True:
            task = voice_queue.get()
            if verbose:
                print('VoiceProcessor received', task)
            if task is None:
                break
            handle, voice_filename = mkstemp(prefix='voice-', suffix='.oga')
            handle, converted_audio_filename = mkstemp(prefix='converted-audio-', suffix='.oga')
            bot.sendChatAction(task['chat_id'], action='upload_audio')
            bot.download_file(task['file_id'], voice_filename)
            audiotools.open(voice_filename).convert(converted_audio_filename, audiotools.VorbisAudio)
            pygame.mixer.music.load(converted_audio_filename)
            pygame.mixer.music.play()
            os.remove(converted_audio_filename)
            os.remove(voice_filename)
            bot.sendMessage(task['chat_id'], 'Voice message played.')
            voice_queue.task_done()


class UploadDirectoryEventHandler(FileSystemEventHandler):

    def __init__(self, *args, **kwargs):
        super(UploadDirectoryEventHandler, self).__init__()
        self.max_photo_size = kwargs.get('max_photo_size', 1280)
        self.do_send_videos = kwargs.get('send_videos', True)
        self.do_send_photos = kwargs.get('send_photos', False)

    def on_created(self, event):
        if not event.is_directory:
            filename, ext = os.path.splitext(os.path.basename(event.src_path))
            ext = ext.lower()
            if ext in ['.jpg', '.png']:
                self.process_photo(event.src_path)
            elif ext in ['.avi', '.mp4', '.mkv', '.m4v', '.mov', '.mpg']:
                self.process_video(event.src_path)
            else:
                if verbose:
                    print('Detected file of unknown type: {:s}'.format(event.src_path))

    def process_photo(self, src_photo_filename):
        global authorized_users, alerting_on
        while os.stat(src_photo_filename).st_size == 0:  # make sure file is written
            time.sleep(0.1)
        if verbose:
            print('New photo file detected: {}'.format(src_photo_filename))
        dst_photo_filename = src_photo_filename
        if alerting_on and self.do_send_photos:
            # TODO: move block to thread (???)
            if self.max_photo_size:
                im = Image.open(src_photo_filename)
                if im.width > self.max_photo_size or im.height > self.max_photo_size:
                    im.thumbnail((self.max_photo_size, self.max_photo_size), Image.BILINEAR)
                    handle, dst_photo_filename = mkstemp(prefix='smarthomebot-', suffix='.jpg')
                    if verbose:
                        print('resizing photo to {} ...'.format(dst_photo_filename))
                    im.save(dst_photo_filename, format='JPEG', quality=87)
                    os.remove(src_photo_filename)
                im.close()
            for user in authorized_users:
                if verbose:
                    print('Sending photo {} ...'.format(dst_photo_filename))
                bot.sendPhoto(user, open(dst_photo_filename, 'rb'),
                              caption=datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S'))
        os.remove(dst_photo_filename)

    def process_video(self, src_video_filename):
        while os.stat(src_video_filename).st_size == 0:  # make sure file is written
            time.sleep(0.1)
        if verbose:
            print('New video file detected: {}'.format(src_video_filename))
        if alerting_on and self.do_send_videos and path_to_ffmpeg:
            video_queue.put({'src_filename': src_video_filename})
        else:
            os.remove(src_video_filename)


class ChatUser(telepot.helper.ChatHandler):

    IdleMessages = ['tüdelü …', '*gähn*', 'Mir ist langweilig.', 'Chill dein Life! Alles cool hier.',
                    'Hier ist tote Hose.', 'Nix los hier …', 'Scheint niemand zu Hause zu sein.',
                    'Sanft ruht der See.', 'Hallo-o!!!', 'Alles cool, Digga.', 'Ich kuck und kuck, aber nix passiert.',
                    'Das Adlerauge ist wachsam, sieht aber nüscht.', 'Nix tut sich.',
                    'Mach du dein Ding. Ich mach hier meins.', 'Alles voll secure in da house.']

    def __init__(self, *args, **kwargs):
        global verbose, cameras
        super(ChatUser, self).__init__(*args, **kwargs)
        self.timeout_secs = kwargs.get('timeout')
        self.verbose = verbose
        self.cameras = cameras
        self.snapshot_job = None
        self.threads = []

    def open(self, initial_msg, seed):
        content_type, chat_type, chat_id = telepot.glance(initial_msg)
        self.init_scheduler(chat_id)

    def cleanup(self):
        while len(self.threads) > 0:
            self.threads.pop().join()

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
                    kwargs={'bot': self.bot,
                            'chat_id': chat_id,
                            'cameras': self.cameras.values()})
        else:
            if type(self.snapshot_job) is Job:
                self.snapshot_job.remove()

    def on__idle(self, event):
        global alerting_on
        if alerting_on:
            ridx = random.randint(0, len(ChatUser.IdleMessages) - 1)
            self.sender.sendMessage(ChatUser.IdleMessages[ridx], parse_mode='Markdown')
        self.cleanup()

    def on_close(self, msg):
        if self.verbose:
            print('on_close() called. {}'.format(msg))
        if type(self.snapshot_job) is Job:
            self.snapshot_job.remove()
        self.cleanup()
        return True

    def send_snapshot_menu(self):
        kbd = [ InlineKeyboardButton(text=self.cameras[c]['name'], callback_data=c)
                for c in self.cameras.keys() ]
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
        if self.cameras.get(query_data):
            self.bot.answerCallbackQuery(query_id,
                                         text='Schnappschuss von deiner Kamera "{}"'.format(query_data))
            snapshot_queue.put({'cameras': [self.cameras[query_data]],
                                'chat_id': from_id,
                                'bot': self.bot,
                                'callback': lambda: self.send_snapshot_menu()})
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
            if self.verbose:
                pprint(msg)
            msg_text = msg['text']
            if msg_text.startswith('/start'):
                self.sender.sendMessage('*Hallo, ich bin dein Heimüberwachungs-Bot!* [' + APPVERSION + ']' +
                                        chr(0x1F916) + "\n\n"
                                        'Ich benachrichtige dich, wenn deine Webcams Bewegungen '
                                        'und laute Geräusche erkannt haben '
                                        'und sende dir ein Video von dem Vorfall.' + "\n",
                                        parse_mode='Markdown')
                self.send_main_menu()
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
                                                                      kwargs={'bot': self.bot,
                                                                              'chat_id': chat_id,
                                                                              'cameras': self.cameras.values()})
                                self.sender.sendMessage('Schnappschüsse sind aktiviert. '
                                                        'Das Intervall ist auf {} Sekunden eingestellt.'
                                                        .format(interval))
                            else:
                                if type(self.napshot_job) is Job:
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
            voice_queue.put({'file_id': msg['voice']['file_id'],
                             'chat_id': chat_id})
        else:
            self.sender.sendMessage('Dein "{}" ist im Nirwana gelandet ...'.format(content_type))


# global variables needed for ChatHandler (which unfortunately doesn't allow extra **kwargs)
authorized_users = None
cameras = None
verbose = False
settings = easydict()
scheduler = BackgroundScheduler()
bot = None
alerting_on = True
snapshot_queue = queue.Queue()
video_queue = queue.Queue()
voice_queue = queue.Queue()
snapshooter = Snapshooter()
video_processor = VideoProcessor()
voice_processor = VoiceProcessor()
path_to_ffmpeg = None

def main():
    global bot, authorized_users, cameras, verbose, settings, scheduler, path_to_ffmpeg
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

    pygame.mixer.pre_init(frequency=48000, size=-16, channels=2, buffer=4096)
    pygame.mixer.init()
    timeout_secs = config.get('timeout_secs', 10 * 60)
    cameras = config.get('cameras', [])
    image_folder = config.get('image_folder', '/home/ftp-upload')
    path_to_ffmpeg = config.get('path_to_ffmpeg')
    max_photo_size = config.get('max_photo_size', 1280)
    verbose = config.get('verbose')
    send_videos = config.get('send_videos', True)
    send_photos = config.get('send_photos', False)
    bot = telepot.DelegatorBot(telegram_bot_token, [
        include_callback_query_chat_id(pave_event_space())(per_chat_id_in(authorized_users, types='private'),
                                                           create_open,
                                                           ChatUser,
                                                           timeout=timeout_secs)
    ])

    if verbose:
        print('Starting threads ...')
    snapshooter.start()
    video_processor.start()
    voice_processor.start()

    if verbose:
        print('Monitoring {} ...'.format(image_folder))
    scheduler.start()
    event_handler = UploadDirectoryEventHandler(
        max_photo_size=max_photo_size,
        send_photos=send_photos,
        send_videos=send_videos,
        ignore_directories=True)
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

    snapshot_queue.join()
    video_queue.join()
    voice_queue.join()
    snapshot_queue.put(None)
    video_queue.put(None)
    voice_queue.put(None)
    snapshooter.join()
    video_processor.join()
    voice_processor.join()


if __name__ == '__main__':
    main()
