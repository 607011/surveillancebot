# How to install SurveillanceBot on Raspbian

## Get prerequisites

```
sudo apt-get install git python3 python3-pip libyaml-cpp-dev
```

## Get sources

Change to a directory where you normally save 3rd party code in, e.g. ~/Workspace, then clone the repository:

```
cd ~/Workspace
git clone https://github.com/ola-ct/surveillancebot.git
```

The code is now contained in the subdirectory "surveillancebot".

## Audio

OGG/Opus support and the Python modules `audiotools` and `pygame` are needed to process incoming voice messages.

### Install OGG/Opus support

```shell
sudo apt-get install opus-tools libopusfile-dev libopus-dev \
  python3-dev libvorbis-dev
```

You can safely ignore the many warnings issued by the compiler when installing the pygame module.

### Install audiotools

The Python [`audiotools`](http://audiotools.sourceforge.net/) module is needed to convert incoming audio messages ([OGG/Opus](https://en.wikipedia.org/wiki/Opus_(audio_format)) encoded) into [OGG/Vorbis](https://en.wikipedia.org/wiki/Vorbis) encoded messages. Only the latter can be played via functions contained in the `pygame` module. The pip-installable `audiotools` currently is missing a file. Therefore it cannot be installed with `pip`, instead it has to be compiled from source. We've added the necessary submodule to the SurveillanceBot repository. Change to submodule's directory, initialize the submodule and fetch the code from its repository, then build and install it by typing: 

```shell
cd surveillancebot/python-audio-tools
git submodule init
git submodule update
sudo python3 setup.py install
```

### Install pygame prerequisites

`pygame` is needed to play audio. Install the module with the following command:

```shell
sudo apt-get install python3-dev python3-numpy \
  libsdl-dev libsdl-image1.2-dev libsdl-mixer1.2-dev \
  libsdl-ttf2.0-dev libsmpeg-dev libportmidi-dev libavformat-dev \
  libswscale-dev 
```

## Install other required modules

```shell
cd Workspace
sudo pip3 install -r requirements.txt
```


## Install ffmpeg

The command-line utility ffmpeg converts videos received from the surveillance cameras to a format suitable for Telegram. Unfortunately, Raspbian doesn't come with an ffmpeg binary. You have to compile it by yourself. 

Telegram prefers H.264 encoded videos. First, you have to get and compile the appropriate library:

```shell
mkdir -p ~/Developer
cd ~/Developer
git clone --depth 1 git://git.videolan.org/x264
cd x264
./configure --host=arm-unknown-linux-gnueabi --enable-static --disable-opencl
make -j 4
sudo make install
```

Then you can build ffmpeg with H.264 support enabled:

```shell
cd ..
git clone --depth 1 git://source.ffmpeg.org/ffmpeg.git
cd ffmpeg
sudo ./configure --arch=armel --target-os=linux --enable-gpl --enable-libx264 --enable-nonfree
make -j 4
sudo make install
```

# How to configure SurveillanceBot

SurveillanceBot reads its configuration from the file smarthomebot-config.json.

A sample configuration looks like this:

```JSON
{
  "telegram_bot_token": "123456789:ASZFACFyZdgPAA-55-jqUU-Jimlql0NIlSC",
  "timeout_secs": 3600,
  "image_folder": "/home/ftp-upload",
  "authorized_users": [ 784132858 ],
  "path_to_ffmpeg": "/usr/local/bin/ffmpeg",
  "max_photo_size": 1280,
  "cameras": {
    "livingroom": {
      "name": "living room",
      "address": "cam.ip",
      "snapshot_url": "http://cam.ip/snapshot.jpg",
      "username": null,
      "password": null
    }
  },
  "audio": {
    "enabled": false
  },
  "verbose": true,
  "send_photos": false,
  "send_videos": true,
  "send_text": false,
  "send_documents": false
}
```

`telegram_bot_token` TODO…

`timeout_secs` TODO…

`image_folder` TODO…

`authorized_users` TODO…

`path_to_ffmpeg` TODO…

`max_photo_size` TODO…

`cameras` TODO…

`audio` TODO…

`verbose` TODO…

`send_photos` TODO…

`send_videos` TODO…

`send_text` TODO…

`send_documents` TODO…
