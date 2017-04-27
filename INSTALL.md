# How to install SurveillanceBot on Raspbian

## Get prerequisites

```
sudo apt-get install git libyaml-cpp-dev \
  python3 python3-pip python3-dev python3-numpy \
  libsdl-dev libsdl-image1.2-dev libsdl-mixer1.2-dev \
  libsdl-ttf2.0-dev libsmpeg-dev libportmidi-dev libavformat-dev \
  libswscale-dev 
```

## Get sources

Change to a directory where you normally save 3rd party code in, e.g. ~/Workspace, then clone the repository:

```
cd ~/Workspace
git clone https://github.com/ola-ct/surveillancebot.git
```

The code is now contained in the subdirectory "surveillancebot".

## Install Python modules

```shell
cd Workspace
sudo pip3 install -r requirements.txt
```

## Install ffmpeg

The command-line utility ffmpeg converts videos received from the surveillance cameras and audio data received from authorized users to a format suitable for Telegram respectively to be played on the local audio device. Unfortunately, Raspbian doesn't come with an ffmpeg binary. You have to compile it by yourself. 

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

After that build ffmpeg with H.264 support enabled:

```shell
cd ..
git clone --depth 1 git://source.ffmpeg.org/ffmpeg.git
cd ffmpeg
sudo ./configure --arch=armel --target-os=linux --enable-gpl --enable-libx264 --enable-libvorbis --enable-nonfree
make -j 4
sudo make install
```

Get a coffee, tea or something else before continuing with the [configuration](CONFIG.md); compilation will take 20 minutes or so.