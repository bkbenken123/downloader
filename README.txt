# YouTube Downloader

A lightweight desktop YouTube downloader built with **Python**, **yt-dlp**, **FFmpeg**, and **Tkinter**. Download videos, extract audio, or save thumbnails through a simple graphical interface.

---

## Features

* Download videos using **yt-dlp**
* Download audio only
* Download video thumbnails
* Support for multiple output formats and codecs
* Automatically detects required binaries locally or from your system **PATH**

---

## Requirements

* Python 3.10 or newer
* yt-dlp
* FFmpeg
* FFprobe

### Binary Locations

The application first looks for the required executables in the following directory:

```text
project/
│
├── binaries/
│   ├── ffmpeg.exe
│   ├── ffprobe.exe
│   └── yt-dlp.exe
│
└── downloader.py
```

If any binaries are not found locally, the application will search your system **PATH**.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/yourusername/youtube-downloader.git
cd youtube-downloader
```

Run the application:

```bash
python downloader.py
```

---

## License

Licensed under the **MIT License**.

---

## Disclaimer

This project is intended for downloading content that you own or are authorized to access. You are responsible for complying with applicable copyright laws and the terms of service of the websites you use.
