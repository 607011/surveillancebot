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

OGG/Opus support and the Python modules `audiotools` and `pygame` and are needed to process incoming voice messages.

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
sudo make install
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


# How to configure SurveillanceBot

```
TODO
```
