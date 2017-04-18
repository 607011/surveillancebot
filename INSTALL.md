# How to install SurveillanceBot 

## Get sources

Change to a directory where you normally save 3rd party code in, e.g. ~/Workspace, then clone the repository:

```
cd ~/Workspace
git clone https://github.com/ola-ct/surveillancebot.git
```

The code is now contained in the subdirectory "surveillancebot".

## Audio

Audiotools, Pygame and OPUS/OGG support are needed to process incoming voice messages.

### Install OPUS/OGG support

```
sudo apt-get install opus-tools libopusfile-dev libopus-dev python-dev libvorbis-dev
```

### Install audiotools

```
# TODO
```

### Install pyGame

```
sudo apt-get install libsdl-dev libsdl-image1.2-dev libsdl-mixer1.2-dev libsdl-ttf2.0-dev \
  libsmpeg-dev libportmidi-dev libavformat-dev libswscale-dev \
  python3-dev python3-numpy
sudo pip install pygame
```


