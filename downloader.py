#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from functools import lru_cache
from tkinter import filedialog, messagebox, ttk
from typing import Iterable, Optional

SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))
APP_VERSION = "2026.07.29-cpu-default-no-test-buttons-r3"
AMD_PCI_VENDOR_ID = "0x1002"
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
ENCODER_BACKENDS = ("AMD", "INTEL", "NVIDIA", "CPU")

DEFAULT_CONFIG = {
    "encoder_backend": "CPU",
    "default_download_dir": os.path.expanduser("~/Downloads"),
    "download_playlist": True,
}



# ---------------------------------------------------------------------------
# Codec configuration
# ---------------------------------------------------------------------------

AUDIO_FFMPEG_CODEC = {
    "aac": "aac",
    "opus": "libopus",
    "flac": "flac",
    "lpcm": "pcm_s16le",
    "mpeg-1": "libmp3lame",
    "mpeg-2": "mp2",
    "copy": None,
}

# Exact audio-codec list requested from the reference script.
AUDIO_CODECS = [
    "aac",
    "opus",
    "flac",
    "lpcm",
    "mpeg-1",
    "mpeg-2",
    "copy",
]

CPU_VIDEO_ENCODER_ARGS = {
    "copy": ["-c:v", "copy"],
    "h264": ["-c:v", "libx264"],
    "h265": ["-c:v", "libx265"],
    "vp9": ["-c:v", "libvpx-vp9"],
    "av1": ["-c:v", "libaom-av1"],
    "prores_422": ["-c:v", "prores_ks", "-profile:v", "3"],
    "dnxhr_sq": ["-c:v", "dnxhd", "-profile:v", "dnxhr_sq"],
    "dnxhr_hq": ["-c:v", "dnxhd", "-profile:v", "dnxhr_hq"],
}

# Exact video-codec list requested from the reference script.
VIDEO_CODECS = [
    "copy",
    "h264",
    "h265",
    "vp9",
    "av1",
    "prores_422",
    "dnxhr_sq",
    "dnxhr_hq",
]

# Exact container lists requested from the reference script.
VIDEO_CONTAINERS = ["mp4", "mkv", "webm", "mov"]
AUDIO_CONTAINERS = ["mp3", "m4a", "wav", "flac", "opus"]
THUMBNAIL_CONTAINERS = ["jpg", "png", "webp"]

GPU_ENCODER_CANDIDATES = {
    "AMD": {
        "h264": ["h264_amf"],
        "h265": ["hevc_amf"],
        "av1": ["av1_amf"],
    },
    "INTEL": {
        "h264": ["h264_qsv"],
        "h265": ["hevc_qsv"],
        "vp9": ["vp9_qsv"],
        "av1": ["av1_qsv"],
    },
    "NVIDIA": {
        "h264": ["h264_nvenc"],
        "h265": ["hevc_nvenc"],
        "av1": ["av1_nvenc"],
    },
}

GPU_ENCODER_LABELS = {
    "h264_amf": "AMD AMF H.264",
    "hevc_amf": "AMD AMF HEVC",
    "av1_amf": "AMD AMF AV1",
    "h264_qsv": "Intel QSV H.264",
    "hevc_qsv": "Intel QSV HEVC",
    "vp9_qsv": "Intel QSV VP9",
    "av1_qsv": "Intel QSV AV1",
    "h264_nvenc": "NVIDIA NVENC H.264",
    "hevc_nvenc": "NVIDIA NVENC HEVC",
    "av1_nvenc": "NVIDIA NVENC AV1",
}

# These are intermediate/download remnants that can be removed after a final
# output has been successfully created.
CLEANUP_EXTS = {
    ".part",
    ".ytdl",
    ".webm",
    ".m4a",
    ".mkv",
    ".mp4",
    ".mka",
    ".opus",
    ".temp",
    ".tmp",
    ".mp2",
}


# ---------------------------------------------------------------------------
# Configuration and yt-dlp startup update
# ---------------------------------------------------------------------------


def _validated_config(raw: object) -> dict:
    config = dict(DEFAULT_CONFIG)
    if not isinstance(raw, dict):
        return config

    backend = raw.get("encoder_backend")
    if isinstance(backend, str) and backend.upper() in ENCODER_BACKENDS:
        config["encoder_backend"] = backend.upper()

    directory = raw.get("default_download_dir")
    if isinstance(directory, str) and directory.strip():
        config["default_download_dir"] = os.path.abspath(os.path.expanduser(directory.strip()))

    playlist = raw.get("download_playlist")
    if isinstance(playlist, bool):
        config["download_playlist"] = playlist

    return config


def load_config() -> tuple[dict, Optional[str]]:
    if not os.path.isfile(CONFIG_PATH):
        return dict(DEFAULT_CONFIG), None

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            return _validated_config(json.load(handle)), None
    except Exception as exc:
        return dict(DEFAULT_CONFIG), f"Could not read config.json; defaults were loaded: {exc}"


def save_config(config: dict) -> None:
    normalized = _validated_config(config)
    changed = {
        key: value
        for key, value in normalized.items()
        if value != DEFAULT_CONFIG[key]
    }

    if not changed:
        try:
            if os.path.isfile(CONFIG_PATH):
                os.remove(CONFIG_PATH)
        except OSError as exc:
            raise OSError(f"Could not remove config.json: {exc}") from exc
        return

    temporary_path = CONFIG_PATH + ".tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as handle:
            json.dump(changed, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary_path, CONFIG_PATH)
    except Exception:
        try:
            if os.path.isfile(temporary_path):
                os.remove(temporary_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# General utilities
# ---------------------------------------------------------------------------


def find_local_executable(candidates: Iterable[str]) -> Optional[str]:
    """Find an executable in binaries/, beside the script, or on PATH."""
    candidates = list(candidates)

    for directory in (os.path.join(SCRIPT_DIR, "binaries"), SCRIPT_DIR):
        for candidate in candidates:
            path = os.path.join(directory, candidate)
            if os.path.isfile(path):
                return os.path.abspath(path)

    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return os.path.abspath(path)

    return None


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip().rstrip(".")
    return cleaned or "download"


def is_playlist_info(info: object) -> bool:
    return isinstance(info, dict) and bool(info.get("entries"))


def command_text(cmd: list[str]) -> str:
    """Format a command for logs without changing what is executed."""
    return subprocess.list2cmdline([str(part) for part in cmd])


def get_ytdlp_command() -> Optional[list[str]]:
    executable = find_local_executable(["yt-dlp.exe", "yt-dlp", "yt_dlp.exe", "yt_dlp"])
    if executable:
        return [executable]

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode == 0:
            return [sys.executable, "-m", "yt_dlp"]
    except Exception:
        pass

    return None


def _run_update_command(cmd: list[str], timeout: int = 180) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = "\n".join(
            part.strip() for part in (proc.stdout, proc.stderr) if part and part.strip()
        )
        return int(proc.returncode), output
    except subprocess.TimeoutExpired:
        return -1, "Update command timed out."
    except Exception as exc:
        return -1, str(exc)


def update_ytdlp_installation() -> tuple[bool, list[str]]:
    messages: list[str] = []
    executable = find_local_executable(["yt-dlp.exe", "yt-dlp", "yt_dlp.exe", "yt_dlp"])

    if executable:
        code, output = _run_update_command([executable, "-U"])
        messages.append(f"yt-dlp standalone updater: {executable}")
        if output:
            messages.extend(line for line in output.splitlines() if line.strip())
        if code == 0:
            command = get_ytdlp_command()
            return command is not None, messages
        messages.append("Standalone update did not succeed; trying pip.")

    pip_base = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "yt-dlp",
        "--disable-pip-version-check",
    ]
    attempts = [pip_base]
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
        attempts.append([*pip_base, "--user"])

    for command in attempts:
        code, output = _run_update_command(command)
        messages.append(f"yt-dlp pip updater: {command_text(command)}")
        if output:
            messages.extend(line for line in output.splitlines() if line.strip())
        if code == 0:
            break
    else:
        return get_ytdlp_command() is not None, messages

    verify_code, version_output = _run_update_command(
        [sys.executable, "-m", "yt_dlp", "--version"], timeout=20
    )
    if version_output:
        messages.append(f"Installed yt-dlp version: {version_output.splitlines()[-1]}")
    return verify_code == 0 or get_ytdlp_command() is not None, messages




def parse_ffmpeg_component_names(output: str) -> set[str]:
    """
    Parse names from `ffmpeg -encoders` or `ffmpeg -decoders`.

    A normal row resembles:
        V....D h264_amf            AMD AMF H.264 encoder

    The old script incorrectly selected the final word ("encoder") instead of
    the second column ("h264_amf").
    """
    names: set[str] = set()
    for raw_line in output.splitlines():
        parts = raw_line.strip().split()
        if len(parts) < 2:
            continue

        flags = parts[0]
        name = parts[1]
        if re.fullmatch(r"[A-Z\.]{6,8}", flags, re.IGNORECASE):
            names.add(name.lower())

    return names


def build_final_path(src: str, target_extension: str) -> str:
    """Turn `Title.temp.mkv.webm` into `Title.<target_extension>`."""
    extension = target_extension.lower().lstrip(".")
    filename = os.path.basename(src)

    # Use the final marker inserted by the output template. A video title may
    # itself contain the text `.temp`, so matching the first occurrence would
    # incorrectly truncate the title.
    marker_index = filename.lower().rfind(".temp.")
    if marker_index >= 0:
        root = filename[:marker_index]
    else:
        root = os.path.splitext(filename)[0]

    return os.path.join(os.path.dirname(src), f"{root}.{extension}")


def unique_existing_paths(paths: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        absolute = os.path.abspath(path)
        key = os.path.normcase(absolute)
        if key in seen or not os.path.isfile(absolute):
            continue
        seen.add(key)
        result.append(absolute)
    return result



def snapshot_temp_files(folder: str) -> dict[str, tuple[int, int]]:
    """Record temp-file mtimes/sizes so stale files are never reconverted."""
    snapshot: dict[str, tuple[int, int]] = {}
    try:
        names = os.listdir(folder)
    except OSError:
        return snapshot
    for name in names:
        if ".temp." not in name.lower():
            continue
        path = os.path.abspath(os.path.join(folder, name))
        if not os.path.isfile(path):
            continue
        try:
            stat = os.stat(path)
            snapshot[os.path.normcase(path)] = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            continue
    return snapshot


# ---------------------------------------------------------------------------
# FFmpeg capability detection
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def detect_ffmpeg_features() -> dict:
    result = {
        "ffmpeg": None,
        "ffprobe": None,
        "hwaccels": set(),
        "encoders": set(),
        "decoders": set(),
    }

    ffmpeg = find_local_executable(["ffmpeg.exe", "ffmpeg"])
    ffprobe = find_local_executable(["ffprobe.exe", "ffprobe"])
    result["ffmpeg"] = ffmpeg
    result["ffprobe"] = ffprobe

    if not ffmpeg:
        return result

    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-hwaccels"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        for line in (proc.stdout + proc.stderr).splitlines():
            value = line.strip().lower()
            if not value or value.startswith("hardware acceleration"):
                continue
            if re.fullmatch(r"[a-z0-9_+-]+", value):
                result["hwaccels"].add(value)
    except Exception:
        pass

    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        result["encoders"] = parse_ffmpeg_component_names(proc.stdout + proc.stderr)
    except Exception:
        pass

    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-decoders"],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        result["decoders"] = parse_ffmpeg_component_names(proc.stdout + proc.stderr)
    except Exception:
        pass

    return result


def _amd_device_init_args() -> list[str]:
    """Create D3D11 and AMF devices on the first AMD DXGI adapter."""
    return [
        "-init_hw_device",
        f"d3d11va=amd_d3d11:,vendor_id={AMD_PCI_VENDOR_ID}",
        "-init_hw_device",
        "amf=amd_amf@amd_d3d11",
        "-filter_hw_device",
        "amd_amf",
    ]



def _encoder_output_args(encoder: str) -> list[str]:
    args = ["-c:v", encoder]
    if encoder.endswith("_amf"):
        args += ["-usage", "transcoding"]
    return args



def usable_gpu_encoders(video_codec: str, backend: str) -> list[str]:
    """Return compiled encoders belonging only to the selected backend."""
    features = detect_ffmpeg_features()
    return [
        encoder
        for encoder in GPU_ENCODER_CANDIDATES.get(backend, {}).get(video_codec, [])
        if encoder in features["encoders"]
    ]


def gpu_decode_strategies(
    encoder: str, backend: str, hwaccels: set[str]
) -> list[tuple[str, list[str]]]:
    """Return hardware-decode prefixes for the selected encoder backend only."""
    if backend == "AMD":
        strategies: list[tuple[str, list[str]]] = []
        if "d3d11va" in hwaccels:
            strategies.append(
                (
                    "AMD D3D11VA decode",
                    [
                        *_amd_device_init_args(),
                        "-hwaccel",
                        "d3d11va",
                        "-hwaccel_device",
                        "amd_d3d11",
                        "-hwaccel_output_format",
                        "d3d11",
                        "-extra_hw_frames",
                        "32",
                    ],
                )
            )
        if "amf" in hwaccels:
            strategies.append(
                (
                    "native AMD AMF decode",
                    [
                        "-hwaccel",
                        "amf",
                        "-hwaccel_output_format",
                        "amf",
                        "-extra_hw_frames",
                        "32",
                    ],
                )
            )
        return strategies

    if backend == "INTEL" and "qsv" in hwaccels:
        return [
            (
                "Intel QSV decode",
                [
                    "-hwaccel",
                    "qsv",
                    "-hwaccel_output_format",
                    "qsv",
                    "-extra_hw_frames",
                    "32",
                ],
            )
        ]

    if backend == "NVIDIA" and "cuda" in hwaccels:
        return [
            (
                "NVIDIA CUDA decode",
                [
                    "-hwaccel",
                    "cuda",
                    "-hwaccel_output_format",
                    "cuda",
                    "-extra_hw_frames",
                    "32",
                ],
            )
        ]

    return []


def probe_input_video(src: str) -> dict:
    features = detect_ffmpeg_features()
    ffprobe = features.get("ffprobe")
    if not ffprobe:
        return {}

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,profile,pix_fmt,width,height",
        "-of",
        "json",
        src,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        if proc.returncode != 0:
            return {}
        data = json.loads(proc.stdout)
        streams = data.get("streams") or []
        return streams[0] if streams else {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Download/conversion worker
# ---------------------------------------------------------------------------


class Worker(threading.Thread):
    def __init__(self, url: str, opts: dict, output_queue: queue.Queue):
        super().__init__(daemon=True)
        self.url = url
        self.opts = opts
        self.q = output_queue
        self.proc: Optional[subprocess.Popen] = None
        self.downloaded_files: list[str] = []

    def _log_capabilities(self) -> None:
        features = detect_ffmpeg_features()
        ffmpeg = features.get("ffmpeg")
        if not ffmpeg:
            self.q.put(("error", "ffmpeg was not found in binaries/, beside the script, or on PATH."))
            return

        self.q.put(("log", f"Build: {APP_VERSION}"))
        self.q.put(("log", f"FFmpeg: {ffmpeg}"))
        if features["hwaccels"]:
            self.q.put(("log", f"FFmpeg hwaccels: {', '.join(sorted(features['hwaccels']))}"))
        else:
            self.q.put(("log", "FFmpeg reports no hardware acceleration methods."))

        selected_codec = self.opts.get("video_codec", "copy")
        backend = self.opts.get("encoder_backend", "CPU")
        self.q.put(("log", f"Forced encoder backend: {backend}"))

        if backend == "CPU" or selected_codec in ("copy", None):
            return

        mapped = GPU_ENCODER_CANDIDATES.get(backend, {}).get(selected_codec, [])
        compiled = [encoder for encoder in mapped if encoder in features["encoders"]]
        if compiled:
            labels = [GPU_ENCODER_LABELS.get(item, item) for item in compiled]
            self.q.put(("log", f"Compiled {backend} encoder(s) for {selected_codec}: {', '.join(labels)}"))
        elif mapped:
            self.q.put(("log", f"No compiled {backend} encoder was found for {selected_codec}."))
        else:
            self.q.put(("log", f"{selected_codec} has no {backend} hardware encoder mapping."))

    def _get_playlist_title(self, url: str) -> Optional[str]:
        if not self.opts.get("download_playlist", True):
            return None

        command = get_ytdlp_command()
        if not command:
            return None

        try:
            proc = subprocess.run(
                [
                    *command,
                    url,
                    "--dump-single-json",
                    "--flat-playlist",
                    "--no-warnings",
                    "--yes-playlist",
                ],
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                if is_playlist_info(data):
                    return data.get("title") or "playlist"
            elif proc.stderr.strip():
                self.q.put(("log", f"Playlist title lookup failed: {proc.stderr.strip()}"))
        except Exception as exc:
            self.q.put(("log", f"Playlist title lookup failed: {exc}"))
        return None

    def _build_outtmpl(self, outdir: str, mode: str) -> tuple[str, str]:
        del mode
        playlist_title = self._get_playlist_title(self.url)
        if playlist_title:
            folder = os.path.join(outdir, sanitize_filename(playlist_title))
        else:
            folder = outdir
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "%(title)s.temp.%(ext)s"), folder

    def _stream_process(self, proc: subprocess.Popen, prefix: Optional[str] = None) -> int:
        self.proc = proc
        try:
            if proc.stdout is not None:
                for line in iter(proc.stdout.readline, ""):
                    if line == "":
                        break
                    text = line.rstrip()
                    if not text:
                        continue
                    if prefix:
                        self.q.put(("log", f"{prefix} {text}"))
                    else:
                        self.q.put(("log", text))
            proc.wait()
            return int(proc.returncode or 0)
        except Exception as exc:
            self.q.put(("log", f"Process streaming error: {exc}"))
            return -1
        finally:
            self.proc = None

    def _run_yt_dlp_subprocess(self, outtmpl: str, mode: str) -> bool:
        command = get_ytdlp_command()
        if not command:
            self.q.put(("error", "yt-dlp was not found after the startup update."))
            return False

        cmd = [
            *command,
            self.url,
            "-o",
            outtmpl,
            "--no-warnings",
            "--no-color",
            "--newline",
            "--force-overwrites",
            "--yes-playlist" if self.opts.get("download_playlist", True) else "--no-playlist",
        ]

        if mode == "thumbnail":
            cmd += ["--skip-download", "--write-thumbnail"]
        elif mode == "audio":
            cmd += ["-f", "bestaudio/best"]
        else:
            cmd += ["-f", "bestvideo+bestaudio/best", "--merge-output-format", "mkv"]

        self.q.put(("log", f"Starting yt-dlp: {command_text(cmd)}"))

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                stdin=subprocess.DEVNULL,
            )
        except Exception as exc:
            self.q.put(("error", f"Failed to start yt-dlp: {exc}"))
            return False

        reported_paths: set[str] = set()
        destination_re = re.compile(r"Destination:\s+(.*)")
        merging_re = re.compile(r'Merging formats into\s*(?:"([^"]+)"|(.+))')
        thumbnail_re = re.compile(r"Writing video thumbnail\s+\d+\s+to:\s+(.*)")

        if proc.stdout is not None:
            for line in iter(proc.stdout.readline, ""):
                if line == "":
                    break
                text = line.rstrip()
                if text:
                    self.q.put(("log", text))

                match = destination_re.search(text)
                if match:
                    reported_paths.add(os.path.abspath(match.group(1).strip().strip('"')))

                match = merging_re.search(text)
                if match:
                    value = (match.group(1) or match.group(2) or "").strip().strip('"')
                    if value:
                        reported_paths.add(os.path.abspath(value))

                match = thumbnail_re.search(text)
                if match:
                    reported_paths.add(os.path.abspath(match.group(1).strip().strip('"')))

        proc.wait()
        if proc.returncode != 0:
            self.q.put(("error", f"yt-dlp exited with code {proc.returncode}"))
            return False

        self.downloaded_files.extend(sorted(reported_paths))
        self.q.put(("log", "yt-dlp finished."))
        return True

    def _find_changed_intermediate_files(
        self,
        out_folder: str,
        before: dict[str, tuple[int, int]],
    ) -> list[str]:
        candidates: list[str] = []
        after = snapshot_temp_files(out_folder)
        for normalized, signature in after.items():
            if before.get(normalized) == signature:
                continue
            # Recover the actual-cased path from the directory scan.
            for name in os.listdir(out_folder):
                path = os.path.abspath(os.path.join(out_folder, name))
                if os.path.normcase(path) == normalized and os.path.isfile(path):
                    candidates.append(path)
                    break
        return unique_existing_paths(candidates)

    def _audio_args(self, audio_codec: Optional[str], mode: str) -> list[str]:
        if mode == "thumbnail":
            return []

        if audio_codec in (None, "copy"):
            return ["-c:a", "copy"]

        ffmpeg_codec = AUDIO_FFMPEG_CODEC.get(audio_codec)
        if not ffmpeg_codec:
            return ["-c:a", "copy"]

        args = ["-c:a", ffmpeg_codec]
        if audio_codec == "aac":
            args += ["-b:a", "192k"]
        elif audio_codec == "opus":
            args += ["-b:a", "160k"]
        elif audio_codec == "mpeg-1":
            # MPEG-1 Audio Layer III, suitable for the .mp3 container.
            args += ["-q:a", "2"]
        elif audio_codec == "mpeg-2":
            args += ["-b:a", "192k"]

        return args

    def _muxer_args(self, dst: str, video_codec: Optional[str]) -> list[str]:
        extension = os.path.splitext(dst)[1].lower()
        args: list[str] = []

        if extension in (".mp4", ".mov"):
            args += ["-movflags", "+faststart"]
        if video_codec == "h265" and extension in (".mp4", ".mov"):
            args += ["-tag:v", "hvc1"]

        return args

    def _run_ffmpeg_attempt(self, label: str, cmd: list[str], dst: str) -> bool:
        try:
            if os.path.isfile(dst):
                os.remove(dst)
        except OSError:
            pass

        self.q.put(("log", f"{label}: {command_text(cmd)}"))
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                stdin=subprocess.DEVNULL,
            )
        except Exception as exc:
            self.q.put(("log", f"{label} could not start: {exc}"))
            return False

        return_code = self._stream_process(proc, prefix="[ffmpeg]")
        if return_code == 0 and os.path.isfile(dst) and os.path.getsize(dst) > 0:
            self.q.put(("log", f"{label} succeeded."))
            return True

        self.q.put(("log", f"{label} failed with code {return_code}."))
        try:
            if os.path.isfile(dst):
                os.remove(dst)
        except OSError:
            pass
        return False

    def _base_video_output_args(
        self,
        dst: str,
        video_args: list[str],
        audio_args: list[str],
        video_codec: str,
        video_filter: Optional[str],
    ) -> list[str]:
        args = [
            "-map",
            "0:v:0?",
            "-map",
            "0:a:0?",
            "-map_metadata",
            "0",
            "-sn",
        ]

        if video_filter:
            args += ["-vf", video_filter]

        args += video_args
        args += audio_args
        args += self._muxer_args(dst, video_codec)
        args += [dst]
        return args

    def _convert_video(
        self,
        ffmpeg: str,
        src: str,
        dst: str,
        video_codec: str,
        audio_codec: str,
    ) -> bool:
        features = detect_ffmpeg_features()
        audio_args = self._audio_args(audio_codec, "video")
        backend = self.opts.get("encoder_backend", "CPU")

        input_info = probe_input_video(src)
        if input_info:
            self.q.put(
                (
                    "log",
                    "Input video: "
                    f"codec={input_info.get('codec_name', 'unknown')}, "
                    f"pixel_format={input_info.get('pix_fmt', 'unknown')}, "
                    f"size={input_info.get('width', '?')}x{input_info.get('height', '?')}",
                )
            )

        if video_codec == "copy":
            cmd = [ffmpeg, "-y", "-nostdin", "-i", src]
            cmd += self._base_video_output_args(
                dst=dst,
                video_args=["-c:v", "copy"],
                audio_args=audio_args,
                video_codec=video_codec,
                video_filter=None,
            )
            return self._run_ffmpeg_attempt("Stream-copy/remux", cmd, dst)

        cpu_video_args = CPU_VIDEO_ENCODER_ARGS.get(video_codec)
        if not cpu_video_args:
            self.q.put(("error", f"No encoder mapping exists for {video_codec}."))
            return False

        if backend == "CPU":
            self.q.put(("log", f"Forced CPU encoder for {video_codec}."))
            cpu_cmd = [ffmpeg, "-y", "-nostdin", "-i", src]
            cpu_cmd += self._base_video_output_args(
                dst=dst,
                video_args=cpu_video_args,
                audio_args=audio_args,
                video_codec=video_codec,
                video_filter=None,
            )
            return self._run_ffmpeg_attempt("CPU decode + CPU encode", cpu_cmd, dst)

        mapped_encoders = GPU_ENCODER_CANDIDATES.get(backend, {}).get(video_codec, [])
        if not mapped_encoders:
            self.q.put(
                (
                    "error",
                    f"The selected {backend} backend is forced, but {video_codec} has no "
                    f"{backend} hardware encoder mapping. Choose CPU or a codec supported "
                    f"by {backend}. No other backend was used.",
                )
            )
            return False

        gpu_encoders = usable_gpu_encoders(video_codec, backend)
        if not gpu_encoders:
            expected = ", ".join(mapped_encoders)
            self.q.put(
                (
                    "error",
                    f"The selected {backend} backend is forced, but FFmpeg does not contain "
                    f"a usable encoder for {video_codec}. Expected: {expected}. "
                    "No other GPU backend and no CPU fallback were used.",
                )
            )
            return False

        for encoder in gpu_encoders:
            label = GPU_ENCODER_LABELS.get(encoder, encoder)
            self.q.put(("log", f"Forced {backend} encoder: {label}"))

            for decode_label, decode_args in gpu_decode_strategies(
                encoder, backend, features["hwaccels"]
            ):
                gpu_decode_cmd = [ffmpeg, "-y", "-nostdin", *decode_args, "-i", src]
                gpu_decode_cmd += self._base_video_output_args(
                    dst=dst,
                    video_args=_encoder_output_args(encoder),
                    audio_args=audio_args,
                    video_codec=video_codec,
                    video_filter=None,
                )
                if self._run_ffmpeg_attempt(
                    f"{decode_label} + {backend} encode ({label})",
                    gpu_decode_cmd,
                    dst,
                ):
                    return True

            self.q.put(
                (
                    "log",
                    f"Hardware decoding failed or was unavailable; retrying CPU decode "
                    f"while keeping {label} encoding.",
                )
            )
            direct_cmd = [ffmpeg, "-y", "-nostdin", "-i", src]
            direct_cmd += self._base_video_output_args(
                dst=dst,
                video_args=_encoder_output_args(encoder),
                audio_args=audio_args,
                video_codec=video_codec,
                video_filter="format=nv12",
            )
            if self._run_ffmpeg_attempt(
                f"CPU decode + {backend} encode ({label})", direct_cmd, dst
            ):
                return True

            if backend == "AMD":
                explicit_cmd = [ffmpeg, "-y", "-nostdin", *_amd_device_init_args(), "-i", src]
                explicit_cmd += self._base_video_output_args(
                    dst=dst,
                    video_args=_encoder_output_args(encoder),
                    audio_args=audio_args,
                    video_codec=video_codec,
                    video_filter="format=nv12,hwupload",
                )
                if self._run_ffmpeg_attempt(
                    f"CPU decode + vendor-bound AMD encode ({label})",
                    explicit_cmd,
                    dst,
                ):
                    return True

        self.q.put(
            (
                "error",
                f"Forced {backend} encoding failed for {video_codec}. "
                "No other GPU backend and no CPU fallback were used.",
            )
        )
        return False

    def _convert_audio(
        self,
        ffmpeg: str,
        src: str,
        dst: str,
        audio_codec: str,
    ) -> bool:
        cmd = [
            ffmpeg,
            "-y",
            "-nostdin",
            "-i",
            src,
            "-map",
            "0:a:0?",
            "-vn",
            "-map_metadata",
            "0",
        ]
        cmd += self._audio_args(audio_codec, "audio")
        cmd += [dst]
        return self._run_ffmpeg_attempt("Audio conversion", cmd, dst)

    def _convert_thumbnail(self, ffmpeg: str, src: str, dst: str) -> bool:
        if os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst)):
            return True

        cmd = [
            ffmpeg,
            "-y",
            "-nostdin",
            "-i",
            src,
            "-frames:v",
            "1",
            dst,
        ]
        return self._run_ffmpeg_attempt("Thumbnail conversion", cmd, dst)

    def _ffmpeg_convert(
        self,
        src: str,
        dst: str,
        mode: str,
        video_codec: Optional[str],
        audio_codec: Optional[str],
    ) -> bool:
        features = detect_ffmpeg_features()
        ffmpeg = features.get("ffmpeg")
        if not ffmpeg:
            self.q.put(("error", "ffmpeg is required for conversion but was not found."))
            return False

        if mode == "video":
            return self._convert_video(
                ffmpeg,
                src,
                dst,
                video_codec or "copy",
                audio_codec or "copy",
            )
        if mode == "audio":
            return self._convert_audio(ffmpeg, src, dst, audio_codec or "copy")
        if mode == "thumbnail":
            return self._convert_thumbnail(ffmpeg, src, dst)

        self.q.put(("error", f"Unknown conversion mode: {mode}"))
        return False

    def _cleanup_after_success(self, source: str, final: str) -> None:
        final_abs = os.path.abspath(final)
        source_abs = os.path.abspath(source)
        directory = os.path.dirname(final_abs)
        final_stem = os.path.splitext(os.path.basename(final_abs))[0]
        removed: list[str] = []

        try:
            filenames = os.listdir(directory)
        except OSError as exc:
            self.q.put(("log", f"Cleanup scan failed: {exc}"))
            return

        for filename in filenames:
            path = os.path.abspath(os.path.join(directory, filename))
            if os.path.normcase(path) == os.path.normcase(final_abs):
                continue

            # Only remove the exact converted source or files carrying the
            # explicit `.temp.` marker inserted by this script. Do not remove
            # arbitrary similarly named media files.
            is_exact_source = os.path.normcase(path) == os.path.normcase(source_abs)
            is_our_temp_file = (
                filename.startswith(final_stem) and ".temp." in filename.lower()
            )
            if not (is_exact_source or is_our_temp_file):
                continue

            try:
                os.remove(path)
                removed.append(path)
            except OSError as exc:
                self.q.put(("log", f"Cleanup failed for {path}: {exc}"))

        if removed:
            self.q.put(("log", f"Removed intermediate files: {', '.join(removed)}"))

    def run(self) -> None:
        out_folder = self.opts.get("outdir", os.path.expanduser("~/Downloads"))
        try:
            self._log_capabilities()

            mode = self.opts["mode"]
            outtmpl, out_folder = self._build_outtmpl(out_folder, mode)
            self.q.put(("log", f"Output template: {outtmpl}"))

            before_download = snapshot_temp_files(out_folder)
            success = self._run_yt_dlp_subprocess(outtmpl, mode)

            if not success:
                self.q.put(("error", "Download failed; conversion was not started."))
                return

            # Prefer paths explicitly reported by yt-dlp. Only use a
            # before/after snapshot when the API did not expose final paths.
            candidates = unique_existing_paths(self.downloaded_files)
            snapshot_candidates = self._find_changed_intermediate_files(
                out_folder, before_download
            )
            candidates = unique_existing_paths([*candidates, *snapshot_candidates])
            candidates.sort(key=lambda path: os.path.getmtime(path))

            if not candidates:
                self.q.put(("error", "No newly downloaded intermediate file was found."))
                return

            successful_outputs: list[str] = []
            successful_pairs: list[tuple[str, str]] = []
            for src in candidates:
                final = build_final_path(src, self.opts["container"])
                self.q.put(("log", f"Converting: {src} -> {final}"))

                converted = self._ffmpeg_convert(
                    src=src,
                    dst=final,
                    mode=mode,
                    video_codec=self.opts.get("video_codec"),
                    audio_codec=self.opts.get("audio_codec"),
                )
                if converted:
                    successful_outputs.append(final)
                    successful_pairs.append((src, final))
                else:
                    self.q.put(("error", f"Conversion failed for {src}"))

            if not successful_outputs:
                self.q.put(("error", "No output files were created successfully."))
                return

            # Cleanup only after every candidate has been processed. This
            # prevents one successful output from deleting another candidate
            # still waiting in the loop.
            for src, final in successful_pairs:
                if os.path.isfile(final):
                    self._cleanup_after_success(src, final)

            self.q.put(("log", f"Created {len(successful_outputs)} output file(s)."))
        except Exception as exc:
            self.q.put(("error", f"Worker exception: {exc}"))
        finally:
            self.q.put(("done", out_folder))


# ---------------------------------------------------------------------------
# Tkinter UI
# ---------------------------------------------------------------------------


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"DOWNLOADER")
        self.root.minsize(900, 520)

        self.q: queue.Queue = queue.Queue()
        self.worker: Optional[Worker] = None
        self.settings, config_warning = load_config()
        self.settings_window: Optional[tk.Toplevel] = None
        self.ytdlp_update_in_progress = True

        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="URL:").pack(side="left")
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(top, textvariable=self.url_var, width=80)
        self.url_entry.pack(side="left", padx=6, fill="x", expand=True)
        ttk.Button(top, text="Paste", command=self.paste_clipboard).pack(side="left", padx=4)

        options_row = ttk.Frame(root, padding=6)
        options_row.pack(fill="x")

        ttk.Label(options_row, text="Mode:").pack(side="left", padx=(0, 6))
        self.mode_var = tk.StringVar(value="video")
        self.mode_dd = ttk.OptionMenu(
            options_row,
            self.mode_var,
            "video",
            "video",
            "audio",
            "thumbnail",
            command=lambda _value: self.on_mode_change(),
        )
        self.mode_dd.pack(side="left", padx=(0, 12))

        ttk.Label(options_row, text="Container:").pack(side="left", padx=(0, 6))
        self.container_var = tk.StringVar(value="mp4")
        self.container_dd = ttk.OptionMenu(
            options_row,
            self.container_var,
            "mp4",
            "mp4",
            "mkv",
            "webm",
            "mov",
            command=lambda _value: self.on_container_change(),
        )
        self.container_dd.pack(side="left", padx=(0, 12))

        ttk.Label(options_row, text="Video codec:").pack(side="left", padx=(0, 6))
        self.video_codec_var = tk.StringVar(value="copy")
        self.video_codec_dd = ttk.OptionMenu(
            options_row,
            self.video_codec_var,
            "copy",
            *VIDEO_CODECS,
        )
        self.video_codec_dd.pack(side="left", padx=(0, 12))

        ttk.Label(options_row, text="Audio codec:").pack(side="left", padx=(0, 6))
        self.audio_codec_var = tk.StringVar(value="copy")
        self.audio_codec_dd = ttk.OptionMenu(
            options_row,
            self.audio_codec_var,
            "copy",
            *AUDIO_CODECS,
        )
        self.audio_codec_dd.pack(side="left", padx=(0, 12))

        output_row = ttk.Frame(root, padding=6)
        output_row.pack(fill="x")
        ttk.Label(output_row, text="Output folder:").pack(side="left")
        self.outdir_var = tk.StringVar(value=self.settings["default_download_dir"])
        ttk.Entry(output_row, textvariable=self.outdir_var, width=60).pack(
            side="left", padx=6, fill="x", expand=True
        )
        ttk.Button(output_row, text="Browse", command=self.browse_outdir).pack(side="left", padx=4)

        controls = ttk.Frame(root, padding=6)
        controls.pack(fill="x")
        self.start_btn = ttk.Button(controls, text="Start", command=self.start, state="disabled")
        self.start_btn.pack(side="left")
        ttk.Button(controls, text="Open Output Folder", command=self.open_outdir).pack(
            side="left", padx=6
        )
        ttk.Button(controls, text="Settings", command=self.open_settings).pack(side="right")

        status_frame = ttk.Frame(root, padding=6)
        status_frame.pack(fill="x")
        self.status_var = tk.StringVar(value="Updating yt-dlp")
        ttk.Label(status_frame, textvariable=self.status_var).pack(side="left")

        log_frame = ttk.LabelFrame(root, text="Log", padding=6)
        log_frame.pack(fill="both", expand=True, padx=6, pady=6)
        self.log_text = tk.Text(log_frame, height=22, state="disabled", wrap="word")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.log(f"App started. Build: {APP_VERSION}")
        self.log(f"Encoder backend: {self.settings['encoder_backend']}")
        self.log(
            "Playlist downloads: "
            + ("enabled" if self.settings["download_playlist"] else "disabled")
        )
        if config_warning:
            self.log(f"WARNING: {config_warning}")
        self.on_mode_change()
        self.root.after(100, self._start_ytdlp_update)
        self.root.after(150, self._process_queue)

    def _start_ytdlp_update(self) -> None:
        threading.Thread(target=self._startup_update_thread, daemon=True).start()

    def _startup_update_thread(self) -> None:
        self.q.put(("log", "Checking for yt-dlp updates at application startup..."))
        success, messages = update_ytdlp_installation()
        for message in messages:
            self.q.put(("log", message))
        self.q.put(("ytdlp_update_done", success, get_ytdlp_command() is not None))

    def open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title("Settings")
        window.transient(self.root)
        window.resizable(False, False)
        window.protocol("WM_DELETE_WINDOW", self._close_settings)

        content = ttk.Frame(window, padding=14)
        content.pack(fill="both", expand=True)

        backend_var = tk.StringVar(value=self.settings["encoder_backend"])
        directory_var = tk.StringVar(value=self.settings["default_download_dir"])
        playlist_var = tk.StringVar(
            value="Yes" if self.settings["download_playlist"] else "No"
        )

        ttk.Label(content, text="Encoder backend:").grid(
            row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 10)
        )
        backend_box = ttk.Combobox(
            content,
            textvariable=backend_var,
            values=ENCODER_BACKENDS,
            state="readonly",
            width=18,
        )
        backend_box.grid(row=0, column=1, sticky="ew", pady=(0, 10))

        ttk.Label(content, text="Default download directory:").grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=(0, 10)
        )
        directory_entry = ttk.Entry(content, textvariable=directory_var, width=52)
        directory_entry.grid(row=1, column=1, sticky="ew", pady=(0, 10))

        def browse_default_directory() -> None:
            initial = directory_var.get().strip() or DEFAULT_CONFIG["default_download_dir"]
            selected = filedialog.askdirectory(parent=window, initialdir=initial)
            if selected:
                directory_var.set(selected)

        ttk.Button(content, text="Browse", command=browse_default_directory).grid(
            row=1, column=2, padx=(8, 0), pady=(0, 10)
        )

        ttk.Label(content, text="Download full playlist:").grid(
            row=2, column=0, sticky="w", padx=(0, 12), pady=(0, 14)
        )
        playlist_box = ttk.Combobox(
            content,
            textvariable=playlist_var,
            values=("Yes", "No"),
            state="readonly",
            width=18,
        )
        playlist_box.grid(row=2, column=1, sticky="w", pady=(0, 14))

        content.columnconfigure(1, weight=1)

        buttons = ttk.Frame(content)
        buttons.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))

        def save_settings() -> None:
            directory = directory_var.get().strip()
            if not directory:
                messagebox.showerror(
                    "Invalid directory",
                    "Enter a default download directory.",
                    parent=window,
                )
                return

            new_settings = {
                "encoder_backend": backend_var.get(),
                "default_download_dir": os.path.abspath(os.path.expanduser(directory)),
                "download_playlist": playlist_var.get() == "Yes",
            }
            try:
                save_config(new_settings)
            except Exception as exc:
                messagebox.showerror(
                    "Settings error",
                    f"Could not save config.json:\n{exc}",
                    parent=window,
                )
                return

            self.settings = _validated_config(new_settings)
            self.outdir_var.set(self.settings["default_download_dir"])
            self.log(f"Settings saved. Encoder backend: {self.settings['encoder_backend']}")
            self.log(
                "Playlist downloads: "
                + ("enabled" if self.settings["download_playlist"] else "disabled")
            )
            self._close_settings()

        def reset_fields() -> None:
            backend_var.set(DEFAULT_CONFIG["encoder_backend"])
            directory_var.set(DEFAULT_CONFIG["default_download_dir"])
            playlist_var.set("Yes" if DEFAULT_CONFIG["download_playlist"] else "No")

        ttk.Button(buttons, text="Save", command=save_settings).pack(side="left")
        ttk.Button(buttons, text="Reset to Defaults", command=reset_fields).pack(
            side="right"
        )

        window.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - window.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - window.winfo_height()) // 2)
        window.geometry(f"+{x}+{y}")
        window.grab_set()
        backend_box.focus_set()

    def _close_settings(self) -> None:
        if self.settings_window is not None:
            try:
                self.settings_window.grab_release()
            except tk.TclError:
                pass
            try:
                self.settings_window.destroy()
            except tk.TclError:
                pass
            self.settings_window = None

    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_option_menu(
        self,
        widget: ttk.OptionMenu,
        variable: tk.StringVar,
        values: list[str],
        callback=None,
    ) -> None:
        menu = widget["menu"]
        menu.delete(0, "end")

        def choose(value: str) -> None:
            variable.set(value)
            if callback is not None:
                callback()

        for value in values:
            menu.add_command(label=value, command=lambda item=value: choose(item))

    def _allowed_video_codecs(self, container: str) -> list[str]:
        # Deliberately show the complete list. Compatibility is validated when
        # Start is pressed instead of silently removing codecs from the menu.
        return list(VIDEO_CODECS)

    def _allowed_audio_codecs(self, mode: str, container: str) -> list[str]:
        if mode in ("video", "audio"):
            return list(AUDIO_CODECS)
        return []

    def on_mode_change(self) -> None:
        mode = self.mode_var.get()

        if mode == "video":
            containers = list(VIDEO_CONTAINERS)
            self._set_option_menu(
                self.container_dd,
                self.container_var,
                containers,
                self.on_container_change,
            )
            if self.container_var.get() not in containers:
                self.container_var.set("mp4")
            self.video_codec_dd.configure(state="normal")
            self.audio_codec_dd.configure(state="normal")
        elif mode == "audio":
            containers = list(AUDIO_CONTAINERS)
            self._set_option_menu(
                self.container_dd,
                self.container_var,
                containers,
                self.on_container_change,
            )
            if self.container_var.get() not in containers:
                self.container_var.set("mp3")
            self.video_codec_dd.configure(state="disabled")
            self.audio_codec_dd.configure(state="normal")
        else:
            containers = list(THUMBNAIL_CONTAINERS)
            self._set_option_menu(
                self.container_dd,
                self.container_var,
                containers,
                self.on_container_change,
            )
            if self.container_var.get() not in containers:
                self.container_var.set("jpg")
            self.video_codec_dd.configure(state="disabled")
            self.audio_codec_dd.configure(state="disabled")

        self.on_container_change()

    def on_container_change(self) -> None:
        mode = self.mode_var.get()
        if mode == "video":
            self._set_option_menu(
                self.video_codec_dd,
                self.video_codec_var,
                list(VIDEO_CODECS),
            )
            if self.video_codec_var.get() not in VIDEO_CODECS:
                self.video_codec_var.set("copy")

        audio_values = self._allowed_audio_codecs(mode, self.container_var.get().lower())
        if audio_values:
            self._set_option_menu(
                self.audio_codec_dd,
                self.audio_codec_var,
                audio_values,
            )
            if self.audio_codec_var.get() not in audio_values:
                self.audio_codec_var.set("copy")
        else:
            self.audio_codec_var.set("N/A")

    def _validate_selection(self) -> Optional[str]:
        mode = self.mode_var.get()
        container = self.container_var.get().lower()
        video = self.video_codec_var.get()
        audio = self.audio_codec_var.get()

        if mode == "video":
            if container not in VIDEO_CONTAINERS:
                return f"Unsupported video container: {container}."
            if video not in VIDEO_CODECS:
                return f"Unsupported video codec: {video}."
            if audio not in AUDIO_CODECS:
                return f"Unsupported audio codec: {audio}."

            video_ok = {
                "mp4": {"copy", "h264", "h265", "vp9", "av1"},
                "mkv": set(VIDEO_CODECS),
                "webm": {"copy", "vp9", "av1"},
                "mov": {"copy", "h264", "h265", "av1", "prores_422", "dnxhr_sq", "dnxhr_hq"},
            }
            audio_ok = {
                "mp4": {"copy", "aac", "flac", "lpcm", "mpeg-1", "mpeg-2"},
                "mkv": set(AUDIO_CODECS),
                "webm": {"copy", "opus"},
                "mov": {"copy", "aac", "flac", "lpcm", "mpeg-1", "mpeg-2"},
            }
            if video not in video_ok[container]:
                return (
                    f"Video codec '{video}' is not compatible with {container}. "
                    "Choose MKV or a compatible video codec."
                )
            if audio not in audio_ok[container]:
                return (
                    f"Audio codec '{audio}' is not compatible with {container}. "
                    "Choose MKV or a compatible audio codec."
                )

            backend = self.settings["encoder_backend"]
            if (
                video != "copy"
                and backend != "CPU"
                and video not in GPU_ENCODER_CANDIDATES.get(backend, {})
            ):
                supported = ", ".join(GPU_ENCODER_CANDIDATES.get(backend, {}).keys())
                return (
                    f"Video codec '{video}' is not supported by the forced {backend} "
                    f"encoder backend. Supported hardware codecs: {supported}. "
                    "Choose CPU in Settings to use the software encoder."
                )

        elif mode == "audio":
            if container not in AUDIO_CONTAINERS:
                return f"Unsupported audio container: {container}."
            if audio not in AUDIO_CODECS:
                return f"Unsupported audio codec: {audio}."

            audio_ok = {
                "mp3": {"copy", "mpeg-1"},
                "m4a": {"copy", "aac"},
                "wav": {"copy", "lpcm"},
                "flac": {"copy", "flac"},
                "opus": {"copy", "opus"},
            }
            if audio not in audio_ok[container]:
                recommended = {
                    "mp3": "mpeg-1",
                    "m4a": "aac",
                    "wav": "lpcm",
                    "flac": "flac",
                    "opus": "opus",
                }[container]
                return (
                    f"Audio codec '{audio}' is not compatible with {container}. "
                    f"Use '{recommended}' or 'copy'."
                )

        elif mode == "thumbnail":
            if container not in THUMBNAIL_CONTAINERS:
                return f"Unsupported thumbnail format: {container}."

        return None

    def paste_clipboard(self) -> None:
        try:
            self.url_var.set(self.root.clipboard_get().strip())
        except Exception:
            self.log("Clipboard is empty or unavailable.")

    def browse_outdir(self) -> None:
        directory = filedialog.askdirectory(initialdir=self.outdir_var.get())
        if directory:
            self.outdir_var.set(directory)

    def open_outdir(self) -> None:
        directory = self.outdir_var.get()
        if not os.path.isdir(directory):
            messagebox.showerror("Error", "Output folder does not exist.")
            return

        if sys.platform == "win32":
            os.startfile(directory)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", directory])
        else:
            subprocess.Popen(["xdg-open", directory])

    def start(self) -> None:
        if self.ytdlp_update_in_progress:
            messagebox.showinfo(
                "yt-dlp update",
                "The startup yt-dlp update is still running.",
            )
            return

        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Already running", "A download is already running.")
            return

        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Enter a URL.")
            return

        if not (
            url.startswith("http://")
            or url.startswith("https://")
            or url.startswith("ytsearch:")
        ):
            proceed = messagebox.askyesno(
                "Validate URL",
                "The URL does not look like HTTP(S). Proceed anyway?",
            )
            if not proceed:
                return

        outdir = self.outdir_var.get().strip() or os.path.expanduser("~/Downloads")
        try:
            os.makedirs(outdir, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Output folder error", str(exc))
            return

        if not find_local_executable(["ffmpeg.exe", "ffmpeg"]):
            messagebox.showerror(
                "ffmpeg missing",
                "Place ffmpeg.exe in the binaries folder or add ffmpeg to PATH.",
            )
            return

        if not get_ytdlp_command():
            messagebox.showerror(
                "yt-dlp missing",
                "Install yt-dlp or place yt-dlp.exe in the binaries folder.",
            )
            return

        mode = self.mode_var.get()
        validation_error = self._validate_selection()
        if validation_error:
            messagebox.showerror("Incompatible codec/container", validation_error)
            return

        options = {
            "mode": mode,
            "container": self.container_var.get(),
            "video_codec": self.video_codec_var.get() if mode == "video" else None,
            "audio_codec": self.audio_codec_var.get() if mode in ("video", "audio") else None,
            "outdir": outdir,
            "encoder_backend": self.settings["encoder_backend"],
            "download_playlist": self.settings["download_playlist"],
        }

        self.status_var.set("Running")
        self.start_btn.configure(state="disabled")
        self.worker = Worker(url, options, self.q)
        self.worker.start()
        self.log("Worker started.")

    def _process_queue(self) -> None:
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]

                if kind == "log":
                    self.log(item[1])
                elif kind == "error":
                    self.log(f"ERROR: {item[1]}")
                elif kind == "done":
                    folder = item[1]
                    self.log(f"Finished. Output folder: {folder}")
                    self.status_var.set("Idle")
                    self.start_btn.configure(state="normal")
                elif kind == "ytdlp_update_done":
                    success, available = bool(item[1]), bool(item[2])
                    self.ytdlp_update_in_progress = False
                    self.start_btn.configure(state="normal")
                    self.status_var.set("Idle")
                    if success:
                        self.log("yt-dlp startup update finished.")
                    elif available:
                        self.log("WARNING: yt-dlp could not be updated, but an existing installation is available.")
                    else:
                        self.log("ERROR: yt-dlp could not be installed or updated.")
                else:
                    self.log(f"Unknown queue message: {item}")
        except queue.Empty:
            pass

        self.root.after(150, self._process_queue)


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
