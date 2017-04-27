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
