#!/usr/bin/env python3
"""
downloader.py

Simple Tkinter GUI wrapper around yt-dlp + ffmpeg.

Features:
- Enter a YouTube (or other supported) URL
- Choose output type: MP3 / M4A / MP4 (video)
- Choose audio quality for audio outputs
- Choose output directory
- Shows progress and logs
- Uses yt_dlp Python library and ffmpeg for conversions via postprocessors

Dependencies:
    pip install yt-dlp
    ffmpeg must be installed and available on PATH

Run:
    python downloader.py
"""
import os
import sys
import threading
import queue
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from yt_dlp import YoutubeDL

# ------ Worker and UI glue ------

class YTDLPWorker(threading.Thread):
    def __init__(self, url, opts, event_queue):
        super().__init__(daemon=True)
        self.url = url
        self.opts = opts
        self.event_queue = event_queue
        self._ydl = None

    def run(self):
        try:
            # prepare YoutubeDL options with progress hook
            def progress_hook(d):
                try:
                    status = d.get('status')
                    if status == 'downloading':
                        downloaded = d.get('downloaded_bytes') or 0
                        total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                        speed = d.get('speed')
                        eta = d.get('eta')
                        percent = (downloaded / total * 100) if total else 0.0
                        self.event_queue.put(('progress', percent, downloaded, total, speed, eta))
                    elif status == 'finished':
                        filename = d.get('filename') or d.get('info_dict', {}).get('_filename')
                        self.event_queue.put(('status', 'finished_downloading', filename))
                    elif status == 'error':
                        self.event_queue.put(('error', d))
                except Exception as e:
                    self.event_queue.put(('error', f'progress_hook error: {e}'))

            self.opts['progress_hooks'] = [progress_hook]
            # Create a YoutubeDL instance and run
            with YoutubeDL(self.opts) as ydl:
                self._ydl = ydl
                self.event_queue.put(('log', f"Starting download: {self.url}"))
                ydl.download([self.url])
                self.event_queue.put(('log', "Download job finished."))
                self.event_queue.put(('done', None))
        except Exception as e:
            self.event_queue.put(('error', str(e)))

# ------ Tkinter GUI ------

class DownloaderApp:
    def __init__(self, root):
        self.root = root
        root.title("ytdlp + ffmpeg Downloader")
        self.event_queue = queue.Queue()

        # URL entry
        frm_top = ttk.Frame(root, padding=8)
        frm_top.pack(fill='x')
        ttk.Label(frm_top, text="URL:").pack(side='left')
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(frm_top, textvariable=self.url_var, width=60)
        self.url_entry.pack(side='left', padx=(6, 6), expand=True, fill='x')

        # Output folder
        frm_folder = ttk.Frame(root, padding=8)
        frm_folder.pack(fill='x')
        ttk.Label(frm_folder, text="Output folder:").pack(side='left')
        self.outdir_var = tk.StringVar(value=os.path.expanduser("~/Downloads"))
        self.outdir_entry = ttk.Entry(frm_folder, textvariable=self.outdir_var, width=40)
        self.outdir_entry.pack(side='left', padx=(6,6), fill='x', expand=True)
        ttk.Button(frm_folder, text="Browse", command=self.browse_outdir).pack(side='left')

        # Format and quality
        frm_opts = ttk.Frame(root, padding=8)
        frm_opts.pack(fill='x')
        ttk.Label(frm_opts, text="Format:").pack(side='left')
        self.format_var = tk.StringVar(value='mp3')
        ttk.OptionMenu(frm_opts, self.format_var, 'mp3', 'mp3', 'm4a', 'mp4').pack(side='left', padx=(6,12))

        ttk.Label(frm_opts, text="Audio quality:").pack(side='left')
        self.quality_var = tk.StringVar(value='192')
        ttk.OptionMenu(frm_opts, self.quality_var, '128', '128', '192', '256', '320').pack(side='left', padx=(6,6))

        # Start button
        frm_actions = ttk.Frame(root, padding=8)
        frm_actions.pack(fill='x')
        self.start_btn = ttk.Button(frm_actions, text="Start", command=self.start_download)
        self.start_btn.pack(side='left')
        ttk.Button(frm_actions, text="Open Output Folder", command=self.open_outdir).pack(side='left', padx=(6,6))

        # Progress bar and status
        frm_progress = ttk.Frame(root, padding=8)
        frm_progress.pack(fill='x')
        self.progress = ttk.Progressbar(frm_progress, orient='horizontal', length=400, mode='determinate')
        self.progress.pack(fill='x', padx=(0,6), expand=True)
        self.status_var = tk.StringVar(value='Idle')
        ttk.Label(frm_progress, textvariable=self.status_var).pack(side='left', padx=(6,0))

        # Log
        frm_log = ttk.Frame(root, padding=8)
        frm_log.pack(fill='both', expand=True)
        ttk.Label(frm_log, text="Log:").pack(anchor='w')
        self.log_text = tk.Text(frm_log, height=12, wrap='word', state='disabled')
        self.log_text.pack(fill='both', expand=True)

        # Poll queue
        self.root.after(200, self.process_events)

        # Worker handle
        self.worker = None

    def browse_outdir(self):
        d = filedialog.askdirectory(initialdir=self.outdir_var.get())
        if d:
            self.outdir_var.set(d)

    def open_outdir(self):
        d = self.outdir_var.get()
        if os.path.isdir(d):
            if sys.platform == 'win32':
                os.startfile(d)
            elif sys.platform == 'darwin':
                subprocess = __import__('subprocess')
                subprocess.Popen(['open', d])
            else:
                subprocess = __import__('subprocess')
                subprocess.Popen(['xdg-open', d])
        else:
            messagebox.showerror("Error", "Output folder does not exist")

    def log(self, text):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', text + '\n')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please enter a URL to download.")
            return

        outdir = self.outdir_var.get()
        if not os.path.isdir(outdir):
            try:
                os.makedirs(outdir, exist_ok=True)
            except Exception as e:
                messagebox.showerror("Output folder", f"Cannot create output folder: {e}")
                return

        # Check ffmpeg
        if not shutil.which('ffmpeg'):
            if not messagebox.askokcancel("ffmpeg not found",
                                          "ffmpeg not found on PATH. yt-dlp conversion will fail without ffmpeg. Continue?"):
                return

        fmt = self.format_var.get()
        quality = self.quality_var.get()

        # Build yt-dlp options
        outtmpl = os.path.join(outdir, '%(title)s.%(ext)s')
        ydl_opts = {
            'outtmpl': outtmpl,
            'noplaylist': False,  # allow playlists by default
            'ignoreerrors': False,
            'quiet': True,  # we'll rely on progress hook and our logs
            'no_warnings': True,
            'restrictfilenames': False,
            'merge_output_format': 'mp4' if fmt == 'mp4' else None,
            'postprocessors': [],
            'format': None,
        }

        if fmt in ('mp3', 'm4a'):
            # download best audio and extract
            ydl_opts['format'] = 'bestaudio/best'
            preferredcodec = 'mp3' if fmt == 'mp3' else 'm4a'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': preferredcodec,
                'preferredquality': quality,
            }, {
                'key': 'FFmpegMetadata'
            }]
        elif fmt == 'mp4':
            # prefer mp4 container + best audio/video
            # fallback to best available
            ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            # ensure merged into mp4 container
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegMerger',
                'preferredformat': 'mp4'
            }, {
                'key': 'FFmpegMetadata'
            }]
        else:
            ydl_opts['format'] = 'best'

        # Reduce console noise (we use progress hooks)
        ydl_opts['logger'] = YTDLLogger(self.event_queue)
        # start worker thread
        self.progress['value'] = 0
        self.status_var.set("Queued")
        self.log(f"Queued: {url} -> {fmt} (quality {quality})")
        self.start_btn.configure(state='disabled')
        self.worker = YTDLPWorker(url, ydl_opts, self.event_queue)
        self.worker.start()

    def process_events(self):
        try:
            while True:
                evt = self.event_queue.get_nowait()
                kind = evt[0]
                if kind == 'progress':
                    _, percent, downloaded, total, speed, eta = evt
                    try:
                        self.progress['value'] = float(percent)
                    except Exception:
                        self.progress['value'] = 0
                    # pretty display
                    total_mb = (total or 0) / (1024*1024)
                    downloaded_mb = (downloaded or 0) / (1024*1024)
                    speed_str = f"{(speed/1024) if speed else 0:.1f} KB/s" if speed else "-"
                    eta_str = f"{eta}s" if eta else "-"
                    self.status_var.set(f"{downloaded_mb:.1f}/{total_mb:.1f} MB ({percent:.1f}%) {speed_str} ETA:{eta_str}")
                elif kind == 'status':
                    _, code, payload = evt
                    if code == 'finished_downloading':
                        self.log(f"Finished downloading raw file: {payload}")
                        self.status_var.set("Finished downloading, postprocessing...")
                elif kind == 'log':
                    _, message = evt
                    self.log(message)
                elif kind == 'error':
                    _, err = evt
                    self.log(f"ERROR: {err}")
                    messagebox.showerror("Error", str(err))
                    self.start_btn.configure(state='normal')
                    self.status_var.set("Error")
                elif kind == 'done':
                    self.log("All done.")
                    self.status_var.set("Done")
                    self.progress['value'] = 100
                    self.start_btn.configure(state='normal')
                else:
                    # unknown
                    self.log(f"Event: {evt}")
        except queue.Empty:
            pass
        finally:
            self.root.after(200, self.process_events)

class YTDLLogger:
    def __init__(self, q):
        self.q = q
    def debug(self, msg):
        # yt-dlp can be very verbose; ignore debug usually
        pass
    def info(self, msg):
        # info-level messages
        self.q.put(('log', msg))
    def warning(self, msg):
        self.q.put(('log', 'WARNING: ' + msg))
    def error(self, msg):
        self.q.put(('error', msg))

if __name__ == '__main__':
    # Basic sanity checks
    try:
        import yt_dlp  # for nicer error if missing
    except Exception:
        print("Missing dependency: yt-dlp. Install with: pip install yt-dlp")
        sys.exit(1)

    root = tk.Tk()
    app = DownloaderApp(root)
    root.geometry('800x520')
    root.mainloop()