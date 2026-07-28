# YouTube Downloader

A desktop YouTube downloader built with Python, yt-dlp, FFmpeg, and Tkinter. Download videos, audio, or thumbnails through a simple graphical interface with support for multiple output formats and codecs.

---

## Features

- Download videos using yt-dlp
- Download audio only
- Download video thumbnails
- Convert videos to multiple codecs and containers
- Convert audio to multiple formats
- Simple desktop interface built with Tkinter
- Automatic playlist folder creation
- Automatic cleanup of temporary files
- Built-in FFmpeg and encoder diagnostics
- Clipboard URL paste support
- Uses local FFmpeg and yt-dlp binaries when available

---

## Supported Video Codecs

- Copy
- H.264
- H.265 / HEVC
- VP9
- AV1
- ProRes 422
- DNxHR SQ
- DNxHR HQ

---

## Supported Audio Codecs

- AAC
- Opus
- FLAC
- LPCM
- MPEG-1 Layer III (MP3)
- MPEG-2 Audio
- Copy

---

## Supported Containers

### Video

- MP4
- MKV
- WEBM
- MOV

### Audio

- MP3
- M4A
- WAV
- FLAC
- OPUS

### Thumbnails

- JPG
- PNG
- WEBP

---

## Requirements

- Python 3.10 or newer
- FFmpeg
- FFprobe
- yt-dlp

The application looks for binaries in the following locations:

```
project/
│
├── binaries/
│   ├── ffmpeg.exe
│   ├── ffprobe.exe
│   └── yt-dlp.exe
│
└── downloader.py
```

If they are not found locally, the application will search your system PATH.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/yourusername/youtube-downloader.git
cd youtube-downloader
```

Install the required Python package:

```bash
pip install yt-dlp
```

Place the following files in the `binaries` folder:

- `ffmpeg.exe`
- `ffprobe.exe`
- `yt-dlp.exe`

Run the application:

```bash
python downloader.py
```

---

## Built-in Diagnostics

The application includes testing tools for verifying:

- FFmpeg installation
- Available hardware acceleration methods
- Video encoder availability
- yt-dlp installation

These tools can help identify configuration issues before starting a download.

---

## Download Modes

### Video

Downloads the highest quality video and audio available, then converts it to the selected codec and container.

### Audio

Downloads the highest quality audio stream and converts it to the selected format.

### Thumbnail

Downloads the video's thumbnail and converts it to the selected image format.

---

## Temporary Files

Intermediate download files are stored using a temporary filename during processing and are automatically removed after a successful conversion.

---

## Built With

- Python
- Tkinter
- yt-dlp
- FFmpeg

---

## License

MIT License

---

## Disclaimer

This project is intended for downloading content that you own or are authorized to access. Users are responsible for complying with applicable copyright laws and the terms of service of the websites they use.