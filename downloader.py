#!/usr/bin/env python3
#this script was made by bkbenken123
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
APP_VERSION = "2026.08.23.3"
AMD_PCI_VENDOR_ID = "0x1002"
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
BINARIES_DIR = os.path.join(SCRIPT_DIR, "binaries")
FFMPEG_SOURCE_DIR = os.path.join(BINARIES_DIR, "ffmpeg")
FFMPEG_OUTPUT_DIR = os.path.join(BINARIES_DIR, "ffmpeg-build")
FFMPEG_OUTPUT_BIN_DIR = os.path.join(FFMPEG_OUTPUT_DIR, "bin")
YTDLP_SOURCE_DIR = os.path.join(BINARIES_DIR, "yt-dlp")
AMF_SOURCE_DIR = os.path.join(BINARIES_DIR, "AMF")
ENCODER_BACKENDS = ("AMD", "INTEL", "NVIDIA", "CPU")

DEFAULT_CONFIG = {
    "encoder_backend": "CPU",
    "default_download_dir": os.path.expanduser("~/Downloads"),
    "download_playlist": True,
    "use_ytdlp_audio_conversion": True,
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

    ytdlp_audio = raw.get("use_ytdlp_audio_conversion")
    if isinstance(ytdlp_audio, bool):
        config["use_ytdlp_audio_conversion"] = ytdlp_audio

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

    for directory in (BINARIES_DIR, SCRIPT_DIR):
        for candidate in candidates:
            path = os.path.join(directory, candidate)
            if os.path.isfile(path):
                return os.path.abspath(path)

    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return os.path.abspath(path)

    return None


def _ffmpeg_built_tool(name: str) -> Optional[str]:
    """Return an FFmpeg tool from the dedicated build output, never the source repo."""
    executable_name = f"{name}.exe" if sys.platform == "win32" else name
    path = os.path.join(FFMPEG_OUTPUT_BIN_DIR, executable_name)
    return os.path.abspath(path) if os.path.isfile(path) else None


def _ffmpeg_source_checkout_exists() -> bool:
    return os.path.isfile(os.path.join(FFMPEG_SOURCE_DIR, "configure"))


FFMPEG_SHARED_DLL_PREFIXES = (
    "avcodec-",
    "avdevice-",
    "avfilter-",
    "avformat-",
    "avutil-",
    "swresample-",
    "swscale-",
)


def _ffmpeg_runtime_dlls() -> list[str]:
    """Return versioned FFmpeg shared-library DLLs from the dedicated build output."""
    if sys.platform != "win32" or not os.path.isdir(FFMPEG_OUTPUT_BIN_DIR):
        return []

    dlls: list[str] = []
    try:
        names = os.listdir(FFMPEG_OUTPUT_BIN_DIR)
    except OSError:
        return []

    for name in names:
        lower = name.lower()
        if not lower.endswith(".dll"):
            continue
        if lower.startswith(FFMPEG_SHARED_DLL_PREFIXES):
            path = os.path.join(FFMPEG_OUTPUT_BIN_DIR, name)
            if os.path.isfile(path):
                dlls.append(os.path.abspath(path))
    return sorted(dlls)


def _ffmpeg_shared_runtime_ready() -> bool:
    """Require all core FFmpeg DLL families on Windows before skipping a build."""
    if sys.platform != "win32":
        return True

    present = {
        next((prefix for prefix in FFMPEG_SHARED_DLL_PREFIXES if os.path.basename(path).lower().startswith(prefix)), None)
        for path in _ffmpeg_runtime_dlls()
    }
    return all(prefix in present for prefix in FFMPEG_SHARED_DLL_PREFIXES)


def _verify_ffmpeg_runtime(ffmpeg: str, ffprobe: str) -> tuple[bool, str]:
    """Actually launch both tools so missing DLL dependencies are caught at startup."""
    for tool in (ffmpeg, ffprobe):
        try:
            proc = subprocess.run(
                [tool, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=20,
                check=False,
            )
        except Exception as exc:
            return False, f"{os.path.basename(tool)} could not start: {exc}"
        if proc.returncode != 0:
            output = (proc.stdout or "").strip()
            if len(output) > 1200:
                output = output[-1200:]
            return False, f"{os.path.basename(tool)} runtime check failed ({proc.returncode}): {output}"
    return True, ""


def find_ffmpeg_executable(name: str) -> Optional[str]:
    """Resolve FFmpeg, preferring the dedicated compiled build output on Windows."""
    # Preserve the earlier Linux rule: use the system FFmpeg on PATH first.
    if sys.platform.startswith("linux"):
        path = shutil.which(name)
        if path:
            return os.path.abspath(path)
        return _ffmpeg_built_tool(name)

    source_tool = _ffmpeg_built_tool(name)
    if source_tool:
        return source_tool

    candidates = [f"{name}.exe", name] if sys.platform == "win32" else [name]
    return find_local_executable(candidates)


def _ytdlp_source_main() -> Optional[str]:
    path = os.path.join(YTDLP_SOURCE_DIR, "yt_dlp", "__main__.py")
    return os.path.abspath(path) if os.path.isfile(path) else None


def find_ytdlp_executable() -> Optional[str]:
    """Resolve a prebuilt yt-dlp executable when one is available."""
    if sys.platform.startswith("linux"):
        path = os.path.join(BINARIES_DIR, "yt-dlp_linux")
        if not os.path.isfile(path):
            return None

        if not os.access(path, os.X_OK):
            try:
                current_mode = os.stat(path).st_mode
                os.chmod(path, current_mode | 0o100)
            except OSError:
                return None

        return os.path.abspath(path)

    # Also accept a locally built PyInstaller executable inside the cloned repo.
    repo_candidates = [
        os.path.join(YTDLP_SOURCE_DIR, "yt-dlp.exe"),
        os.path.join(YTDLP_SOURCE_DIR, "dist", "yt-dlp.exe"),
    ]
    for path in repo_candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)

    return find_local_executable(["yt-dlp.exe", "yt-dlp", "yt_dlp.exe", "yt_dlp"])


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name).strip().rstrip(".")
    return cleaned or "download"


def is_playlist_info(info: object) -> bool:
    return isinstance(info, dict) and bool(info.get("entries"))


def command_text(cmd: list[str]) -> str:
    """Format a command for logs without changing what is executed."""
    return subprocess.list2cmdline([str(part) for part in cmd])


def get_ytdlp_command() -> Optional[list[str]]:
    """Use the cloned yt-dlp source directly when it exists."""
    source_main = _ytdlp_source_main()
    if source_main:
        return [sys.executable, source_main]

    executable = find_ytdlp_executable()
    if executable:
        return [executable]

    # Linux keeps its historical bundled-binary/source-checkout rule.
    if sys.platform.startswith("linux"):
        return None

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


def _run_update_command(
    cmd: list[str],
    timeout: int = 180,
    cwd: Optional[str] = None,
) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
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


def _run_streamed_process(
    cmd: list[str],
    log,
    cwd: Optional[str] = None,
    env: Optional[dict[str, str]] = None,
) -> int:
    """Run a long build command while forwarding each output line to the GUI."""
    log(f"Running: {command_text(cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            stdin=subprocess.DEVNULL,
        )
    except Exception as exc:
        log(f"Could not start build command: {exc}")
        return -1

    if proc.stdout is not None:
        for line in iter(proc.stdout.readline, ""):
            if line == "":
                break
            text = line.rstrip()
            if text:
                log(f"[ffmpeg-build] {text}")

    proc.wait()
    return int(proc.returncode or 0)


def _find_windows_msys2() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (bash.exe, toolchain bin directory, MSYSTEM) for an MSYS2 install."""
    roots: list[str] = []
    for value in (
        os.environ.get("MSYS2_ROOT"),
        r"C:\msys64",
        r"C:\tools\msys64",
        r"C:\msys32",
    ):
        if value and value not in roots:
            roots.append(value)

    path_bash = shutil.which("bash")
    if path_bash:
        normalized = os.path.normpath(path_bash)
        # Typical MSYS2 bash path is <root>\usr\bin\bash.exe.
        root_guess = os.path.dirname(os.path.dirname(os.path.dirname(normalized)))
        if os.path.isfile(os.path.join(root_guess, "usr", "bin", "bash.exe")):
            roots.insert(0, root_guess)

    toolchains = (
        ("ucrt64", "UCRT64", ("gcc.exe", "clang.exe")),
        ("mingw64", "MINGW64", ("gcc.exe", "clang.exe")),
        ("clang64", "CLANG64", ("clang.exe", "gcc.exe")),
    )

    for root in roots:
        bash = os.path.join(root, "usr", "bin", "bash.exe")
        if not os.path.isfile(bash):
            continue
        for subdir, msystem, compiler_names in toolchains:
            toolchain_bin = os.path.join(root, subdir, "bin")
            if any(os.path.isfile(os.path.join(toolchain_bin, item)) for item in compiler_names):
                return os.path.abspath(bash), os.path.abspath(toolchain_bin), msystem

    # Last chance: a shell already configured by the user. The preflight inside
    # the build command will reject Git Bash if no compiler/make is available.
    if path_bash:
        return os.path.abspath(path_bash), None, None

    return None, None, None




def _windows_ffmpeg_build_workspace(log) -> Optional[str]:
    """Choose a writable build path with no spaces (FFmpeg builds dislike them)."""
    candidates = []
    for base in (
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("TEMP"),
        os.environ.get("PUBLIC"),
        r"C:\Users\Public",
    ):
        if not base:
            continue
        candidate = os.path.abspath(os.path.join(base, "DownloaderFFmpegBuild"))
        if " " in candidate:
            continue
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        try:
            os.makedirs(os.path.dirname(candidate), exist_ok=True)
            return candidate
        except OSError:
            continue

    log(
        "ERROR: Could not find a writable Windows build path without spaces. "
        "Set LOCALAPPDATA, TEMP, or PUBLIC to a writable no-space path and run again."
    )
    return None


def _prepare_windows_ffmpeg_workspace(log) -> Optional[str]:
    workspace = _windows_ffmpeg_build_workspace(log)
    if not workspace:
        return None

    configure = os.path.join(workspace, "configure")
    configured = os.path.join(workspace, "ffbuild", "config.mak")

    # Keep a configured partial build so a failed compile can resume next run.
    # If configure never completed, refresh the workspace from the user's clone.
    if not os.path.isfile(configured):
        try:
            if os.path.isdir(workspace):
                shutil.rmtree(workspace)
            elif os.path.exists(workspace):
                os.remove(workspace)

            log(f"Copying FFmpeg source to no-space build workspace: {workspace}")
            shutil.copytree(
                FFMPEG_SOURCE_DIR,
                workspace,
                ignore=shutil.ignore_patterns(
                    ".git",
                    "*.exe",
                    "*.o",
                    "*.a",
                    "*.d",
                    "config.h",
                    "config_components.h",
                ),
            )

            # Never inherit a configure result generated in the original path.
            stale_config = os.path.join(workspace, "ffbuild", "config.mak")
            if os.path.isfile(stale_config):
                os.remove(stale_config)
        except Exception as exc:
            log(f"ERROR: Could not prepare FFmpeg build workspace: {exc}")
            return None

    if not os.path.isfile(configure):
        log(f"ERROR: FFmpeg configure script is missing from build workspace: {workspace}")
        return None

    return workspace



def _prepare_windows_amf_headers(workspace: str, log) -> Optional[str]:
    """Prepare AMD AMF headers so the source build keeps h264/hevc/av1 AMF support."""
    source_headers = os.path.join(AMF_SOURCE_DIR, "amf", "public", "include")

    if not os.path.isfile(os.path.join(source_headers, "core", "Factory.h")):
        git = shutil.which("git")
        if not git:
            log(
                "WARNING: Git is not available, so AMD AMF headers could not be fetched. "
                "FFmpeg will still build, but AMF encoders may be unavailable."
            )
            return None

        if os.path.exists(AMF_SOURCE_DIR):
            log(
                f"WARNING: {AMF_SOURCE_DIR} exists but does not look like a valid AMF checkout; "
                "skipping automatic AMF header setup."
            )
            return None

        log("AMD AMF headers were not found; cloning the official AMF header repository...")
        code = _run_streamed_process(
            [
                git,
                "clone",
                "--depth",
                "1",
                "https://github.com/GPUOpen-LibrariesAndSDKs/AMF.git",
                AMF_SOURCE_DIR,
            ],
            log,
        )
        if code != 0 or not os.path.isfile(os.path.join(source_headers, "core", "Factory.h")):
            log(
                "WARNING: AMD AMF headers could not be prepared. "
                "Continuing with a base FFmpeg build without forced AMF support."
            )
            return None

    include_root = os.path.join(workspace, ".downloader-deps", "include")
    amf_dest = os.path.join(include_root, "AMF")
    try:
        if os.path.isdir(amf_dest):
            shutil.rmtree(amf_dest)
        os.makedirs(include_root, exist_ok=True)
        shutil.copytree(source_headers, amf_dest)
    except OSError as exc:
        log(f"WARNING: Could not stage AMD AMF headers for FFmpeg: {exc}")
        return None

    log("AMD AMF headers are staged for the FFmpeg build.")
    return include_root

def _copy_msys_runtime_dependencies(staged_bin: str, toolchain_bin: Optional[str], log) -> None:
    """Copy non-system MinGW runtime DLL dependencies needed by the staged FFmpeg build."""
    if not toolchain_bin or not os.path.isdir(toolchain_bin):
        return

    objdump_candidates = [
        os.path.join(toolchain_bin, "objdump.exe"),
        shutil.which("objdump"),
    ]
    objdump = next((item for item in objdump_candidates if item and os.path.isfile(item)), None)
    if not objdump:
        log("WARNING: objdump was not found; external MinGW DLL dependencies could not be auto-collected.")
        return

    try:
        queue_paths = [
            os.path.join(staged_bin, name)
            for name in os.listdir(staged_bin)
            if name.lower().endswith((".exe", ".dll"))
            and os.path.isfile(os.path.join(staged_bin, name))
        ]
    except OSError:
        return

    seen: set[str] = set()
    copied: list[str] = []
    while queue_paths:
        binary = queue_paths.pop(0)
        key = os.path.normcase(os.path.abspath(binary))
        if key in seen:
            continue
        seen.add(key)
        try:
            proc = subprocess.run(
                [objdump, "-p", binary],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except Exception:
            continue

        for raw_line in (proc.stdout or "").splitlines():
            match = re.search(r"DLL Name:\s*(.+?)\s*$", raw_line, re.IGNORECASE)
            if not match:
                continue
            dll_name = match.group(1).strip()
            if not dll_name.lower().endswith(".dll"):
                continue
            staged = os.path.join(staged_bin, dll_name)
            if os.path.isfile(staged):
                queue_paths.append(staged)
                continue
            source = os.path.join(toolchain_bin, dll_name)
            if not os.path.isfile(source):
                continue
            try:
                shutil.copy2(source, staged)
                copied.append(dll_name)
                queue_paths.append(staged)
            except OSError as exc:
                log(f"WARNING: Could not copy runtime dependency {dll_name}: {exc}")

    if copied:
        log("Copied MinGW runtime dependency DLL(s): " + ", ".join(sorted(set(copied), key=str.lower)))


def _build_ffmpeg_windows(log) -> bool:
    bash, toolchain_bin, msystem = _find_windows_msys2()
    if not bash:
        log(
            "ERROR: FFmpeg source is present, but an MSYS2 build shell was not found. "
            "Install MSYS2 with make + a MinGW/UCRT64 compiler, then run the downloader again."
        )
        return False

    workspace = _prepare_windows_ffmpeg_workspace(log)
    if not workspace:
        return False

    amf_include_root = _prepare_windows_amf_headers(workspace, log)
    staged_install = os.path.join(workspace, "_shared_install")

    env = os.environ.copy()
    env["FFMPEG_BUILD_WINDOWS"] = workspace
    if amf_include_root:
        env["FFMPEG_AMF_INCLUDE_WINDOWS"] = amf_include_root
    env["CHERE_INVOKING"] = "1"
    env["MSYS2_PATH_TYPE"] = "inherit"
    if msystem:
        env["MSYSTEM"] = msystem
    if toolchain_bin:
        msys_root = os.path.dirname(os.path.dirname(toolchain_bin))
        usr_bin = os.path.join(msys_root, "usr", "bin")
        env["PATH"] = os.pathsep.join([toolchain_bin, usr_bin, env.get("PATH", "")])

    build_script = r"""
set -o pipefail
BUILDROOT="$(cygpath -u "$FFMPEG_BUILD_WINDOWS" 2>/dev/null || printf '%s' "$FFMPEG_BUILD_WINDOWS")"
INSTALLROOT="$BUILDROOT/_shared_install"
cd "$BUILDROOT" || exit 90

if ! command -v make >/dev/null 2>&1; then
    echo "ERROR: GNU make is missing from the MSYS2 environment. Install package: make"
    exit 91
fi
if ! command -v gcc >/dev/null 2>&1 && ! command -v clang >/dev/null 2>&1; then
    echo "ERROR: No MinGW/UCRT64 C compiler was found. Install an MSYS2 MinGW/UCRT64 GCC or Clang toolchain."
    exit 92
fi

EXTRA_FLAGS=()
if [ -n "${FFMPEG_AMF_INCLUDE_WINDOWS:-}" ]; then
    AMF_INCLUDE="$(cygpath -u "$FFMPEG_AMF_INCLUDE_WINDOWS" 2>/dev/null || printf '%s' "$FFMPEG_AMF_INCLUDE_WINDOWS")"
    EXTRA_FLAGS+=(--enable-amf "--extra-cflags=-I$AMF_INCLUDE")
    echo "AMD AMF support requested using staged headers: $AMF_INCLUDE"
fi

if ! command -v nasm >/dev/null 2>&1; then
    echo "NASM was not found; compiling with --disable-x86asm so the first build can still complete."
    EXTRA_FLAGS+=(--disable-x86asm)
fi

if command -v pkg-config >/dev/null 2>&1; then
    if pkg-config --exists x264; then EXTRA_FLAGS+=(--enable-libx264); fi
    if pkg-config --exists x265; then EXTRA_FLAGS+=(--enable-libx265); fi
    if pkg-config --exists vpx; then EXTRA_FLAGS+=(--enable-libvpx); fi
    if pkg-config --exists aom; then EXTRA_FLAGS+=(--enable-libaom); fi
    if pkg-config --exists opus; then EXTRA_FLAGS+=(--enable-libopus); fi
    if pkg-config --exists libmp3lame; then EXTRA_FLAGS+=(--enable-libmp3lame); fi
else
    echo "pkg-config was not found; optional external codec libraries will not be auto-enabled."
fi

# The old workspace may be configured static-only. A DLL build needs a full
# clean reconfigure so --enable-shared actually takes effect.
if [ -f ffbuild/config.mak ]; then
    echo "Removing the previous static/partial FFmpeg configuration..."
    make distclean || exit $?
fi
rm -rf "$INSTALLROOT"
mkdir -p "$INSTALLROOT"

echo "Configuring FFmpeg with shared DLL libraries enabled..."
bash ./configure \
    --prefix="$INSTALLROOT" \
    --disable-doc \
    --disable-ffplay \
    --enable-gpl \
    --enable-version3 \
    --enable-shared \
    --disable-static \
    "${EXTRA_FLAGS[@]}" || exit $?

JOBS="${NUMBER_OF_PROCESSORS:-4}"
echo "Compiling FFmpeg shared build with $JOBS parallel job(s)..."
make -j"$JOBS" || exit $?
echo "Installing ffmpeg.exe, ffprobe.exe and FFmpeg DLLs into the staging folder..."
make install || exit $?
"""

    log(f"FFmpeg source checkout (read-only build input): {FFMPEG_SOURCE_DIR}")
    log(f"FFmpeg compile workspace (separate from repository): {workspace}")
    log(f"FFmpeg final build output: {FFMPEG_OUTPUT_BIN_DIR}")
    log(f"FFmpeg build shell: {bash}")
    log("FFmpeg build type: shared DLLs (--enable-shared --disable-static)")
    if msystem:
        log(f"MSYS2 environment: {msystem}")

    if _run_streamed_process([bash, "-lc", build_script], log, env=env) != 0:
        return False

    staged_bin = os.path.join(staged_install, "bin")
    built_ffmpeg = os.path.join(staged_bin, "ffmpeg.exe")
    built_ffprobe = os.path.join(staged_bin, "ffprobe.exe")
    if not (os.path.isfile(built_ffmpeg) and os.path.isfile(built_ffprobe)):
        log("ERROR: Shared build finished but staged ffmpeg.exe/ffprobe.exe were not produced.")
        return False

    try:
        staged_names = os.listdir(staged_bin)
    except OSError as exc:
        log(f"ERROR: Could not inspect staged FFmpeg build output: {exc}")
        return False

    ffmpeg_dlls = [
        name
        for name in staged_names
        if name.lower().endswith(".dll")
        and name.lower().startswith(FFMPEG_SHARED_DLL_PREFIXES)
        and os.path.isfile(os.path.join(staged_bin, name))
    ]
    present_prefixes = {
        next((prefix for prefix in FFMPEG_SHARED_DLL_PREFIXES if name.lower().startswith(prefix)), None)
        for name in ffmpeg_dlls
    }
    missing_prefixes = [prefix for prefix in FFMPEG_SHARED_DLL_PREFIXES if prefix not in present_prefixes]
    if missing_prefixes:
        log(
            "ERROR: Shared FFmpeg build did not produce all required DLL families. Missing: "
            + ", ".join(prefix.rstrip("-") for prefix in missing_prefixes)
        )
        return False

    _copy_msys_runtime_dependencies(staged_bin, toolchain_bin, log)

    try:
        # Runtime output is deliberately separate from binaries\ffmpeg, which remains
        # a source-only Git checkout. Replace the output bin atomically enough that
        # stale versioned DLLs from an older FFmpeg build cannot be mixed in.
        os.makedirs(FFMPEG_OUTPUT_DIR, exist_ok=True)
        replacement_bin = os.path.join(FFMPEG_OUTPUT_DIR, "bin.new")
        old_bin = os.path.join(FFMPEG_OUTPUT_DIR, "bin.old")
        for path in (replacement_bin, old_bin):
            if os.path.isdir(path):
                shutil.rmtree(path)
            elif os.path.exists(path):
                os.remove(path)
        os.makedirs(replacement_bin, exist_ok=True)

        files_to_copy = ["ffmpeg.exe", "ffprobe.exe"] + [
            name for name in os.listdir(staged_bin) if name.lower().endswith(".dll")
        ]
        copied_dlls: list[str] = []
        for name in files_to_copy:
            src = os.path.join(staged_bin, name)
            if not os.path.isfile(src):
                continue
            shutil.copy2(src, os.path.join(replacement_bin, name))
            if name.lower().endswith(".dll"):
                copied_dlls.append(name)

        # Verify the freshly copied set before making it the active runtime.
        candidate_ffmpeg = os.path.join(replacement_bin, "ffmpeg.exe")
        candidate_ffprobe = os.path.join(replacement_bin, "ffprobe.exe")
        runtime_ok, runtime_error = _verify_ffmpeg_runtime(candidate_ffmpeg, candidate_ffprobe)
        if not runtime_ok:
            log(f"ERROR: Fresh FFmpeg build cannot run from the separate output folder: {runtime_error}")
            shutil.rmtree(replacement_bin, ignore_errors=True)
            return False

        if os.path.isdir(FFMPEG_OUTPUT_BIN_DIR):
            os.replace(FFMPEG_OUTPUT_BIN_DIR, old_bin)
        os.replace(replacement_bin, FFMPEG_OUTPUT_BIN_DIR)
        if os.path.isdir(old_bin):
            shutil.rmtree(old_bin, ignore_errors=True)

        log(f"Installed compiled FFmpeg into separate build folder: {FFMPEG_OUTPUT_BIN_DIR}")
        log(r"The binaries\ffmpeg repository was not used as an output directory.")
        log(f"Copied {len(copied_dlls)} runtime DLL(s) beside FFmpeg.")
        for name in sorted(copied_dlls, key=str.lower):
            log(f"FFmpeg runtime DLL: {name}")
    except OSError as exc:
        log(f"ERROR: Could not install compiled FFmpeg into the separate build folder: {exc}")
        return False

    installed_ffmpeg = os.path.join(FFMPEG_OUTPUT_BIN_DIR, "ffmpeg.exe")
    installed_ffprobe = os.path.join(FFMPEG_OUTPUT_BIN_DIR, "ffprobe.exe")
    runtime_ok, runtime_error = _verify_ffmpeg_runtime(installed_ffmpeg, installed_ffprobe)
    if not runtime_ok:
        log(f"ERROR: Compiled FFmpeg cannot run with the copied DLL set: {runtime_error}")
        return False

    return True

def _build_ffmpeg_posix(log) -> bool:
    """Build FFmpeg outside the source checkout and install into ffmpeg-build/."""
    configure = os.path.join(FFMPEG_SOURCE_DIR, "configure")
    make = shutil.which("make")
    shell = shutil.which("bash") or shutil.which("sh")
    if not shell or not make:
        log("ERROR: FFmpeg source exists, but bash/sh and GNU make are required to compile it.")
        return False

    # Linux normally uses system FFmpeg before reaching this function. For other
    # POSIX systems, keep object files/configuration outside the repository too.
    build_dir = os.path.join(FFMPEG_OUTPUT_DIR, "obj")
    install_dir = os.path.join(FFMPEG_OUTPUT_DIR, "install")
    try:
        os.makedirs(build_dir, exist_ok=True)
        if os.path.isdir(install_dir):
            shutil.rmtree(install_dir)
        os.makedirs(install_dir, exist_ok=True)
    except OSError as exc:
        log(f"ERROR: Could not prepare separate FFmpeg build directories: {exc}")
        return False

    log(f"FFmpeg source checkout (build input): {FFMPEG_SOURCE_DIR}")
    log(f"FFmpeg object/build directory: {build_dir}")
    log(f"FFmpeg final build output: {FFMPEG_OUTPUT_BIN_DIR}")

    # FFmpeg supports configuring from a separate working directory. Use an
    # absolute configure path so generated objects never land in the checkout.
    code = _run_streamed_process(
        [
            shell,
            configure,
            f"--prefix={install_dir}",
            "--disable-doc",
            "--disable-ffplay",
            "--enable-gpl",
            "--enable-version3",
        ],
        log,
        cwd=build_dir,
    )
    if code != 0:
        return False

    jobs = str(os.cpu_count() or 4)
    if _run_streamed_process([make, f"-j{jobs}"], log, cwd=build_dir) != 0:
        return False
    if _run_streamed_process([make, "install"], log, cwd=build_dir) != 0:
        return False

    installed_bin = os.path.join(install_dir, "bin")
    try:
        if os.path.isdir(FFMPEG_OUTPUT_BIN_DIR):
            shutil.rmtree(FFMPEG_OUTPUT_BIN_DIR)
        shutil.copytree(installed_bin, FFMPEG_OUTPUT_BIN_DIR)
    except OSError as exc:
        log(f"ERROR: Could not install FFmpeg into separate build output: {exc}")
        return False
    return True


def ensure_ffmpeg_ready(log) -> bool:
    """Compile the cloned FFmpeg only when the separate build output is not ready."""
    if sys.platform.startswith("linux"):
        system_ffmpeg = shutil.which("ffmpeg")
        system_ffprobe = shutil.which("ffprobe")
        if system_ffmpeg and system_ffprobe:
            log(f"Using system FFmpeg from PATH: {os.path.abspath(system_ffmpeg)}")
            return True

    if _ffmpeg_source_checkout_exists():
        ffmpeg = _ffmpeg_built_tool("ffmpeg")
        ffprobe = _ffmpeg_built_tool("ffprobe")
        dll_ready = _ffmpeg_shared_runtime_ready()

        if ffmpeg and ffprobe and dll_ready:
            runtime_ok, runtime_error = _verify_ffmpeg_runtime(ffmpeg, ffprobe)
            if runtime_ok:
                log("Separate FFmpeg build output already exists and is complete; skipping compilation.")
                log(f"FFmpeg: {ffmpeg}")
                log(f"FFprobe: {ffprobe}")
                if sys.platform == "win32":
                    log(f"FFmpeg runtime DLLs: {len(_ffmpeg_runtime_dlls())} core DLL(s) detected.")
                return True
            log(f"Existing FFmpeg runtime is incomplete or broken: {runtime_error}")

        if sys.platform == "win32" and ffmpeg and ffprobe and not dll_ready:
            log("Existing separate FFmpeg build is static-only or missing shared DLLs; rebuilding with DLLs...")
        else:
            log("Separate FFmpeg build output was not found or is incomplete. Starting first-run compilation...")

        success = (
            _build_ffmpeg_windows(log)
            if sys.platform == "win32"
            else _build_ffmpeg_posix(log)
        )
        if not success:
            return False

        try:
            detect_ffmpeg_features.cache_clear()
        except NameError:
            pass

        ffmpeg = _ffmpeg_built_tool("ffmpeg")
        ffprobe = _ffmpeg_built_tool("ffprobe")
        if ffmpeg and ffprobe and _ffmpeg_shared_runtime_ready():
            runtime_ok, runtime_error = _verify_ffmpeg_runtime(ffmpeg, ffprobe)
            if runtime_ok:
                log("FFmpeg shared build finished successfully in the separate build folder.")
                log(f"FFmpeg: {ffmpeg}")
                log(f"FFprobe: {ffprobe}")
                if sys.platform == "win32":
                    log(f"FFmpeg runtime DLLs: {len(_ffmpeg_runtime_dlls())} core DLL(s) detected.")
                return True
            log(f"ERROR: FFmpeg was built but its shared runtime cannot start: {runtime_error}")
            return False

        log("ERROR: FFmpeg build finished, but the separate executable/shared DLL set is incomplete.")
        return False

    ffmpeg = find_ffmpeg_executable("ffmpeg")
    ffprobe = find_ffmpeg_executable("ffprobe")
    if ffmpeg and ffprobe:
        runtime_ok, runtime_error = _verify_ffmpeg_runtime(ffmpeg, ffprobe)
        if runtime_ok:
            log(f"Using existing FFmpeg installation: {ffmpeg}")
            return True
        log(f"ERROR: Existing FFmpeg installation could not start: {runtime_error}")
        return False

    log(
        f"ERROR: No FFmpeg source checkout was found at {FFMPEG_SOURCE_DIR}, "
        "and no usable prebuilt FFmpeg installation was found."
    )
    return False


def update_ytdlp_installation() -> tuple[bool, list[str]]:
    messages: list[str] = []
    source_main = _ytdlp_source_main()

    if source_main:
        messages.append(f"Using cloned yt-dlp source checkout: {YTDLP_SOURCE_DIR}")
        git = shutil.which("git")
        git_dir = os.path.join(YTDLP_SOURCE_DIR, ".git")
        if git and os.path.isdir(git_dir):
            code, output = _run_update_command(
                [git, "pull", "--ff-only"],
                timeout=180,
                cwd=YTDLP_SOURCE_DIR,
            )
            messages.append("yt-dlp source update: git pull --ff-only")
            if output:
                messages.extend(line for line in output.splitlines() if line.strip())
            if code != 0:
                messages.append(
                    "WARNING: The yt-dlp source checkout could not be updated; "
                    "the existing checkout will still be tested and used."
                )
        elif not git:
            messages.append(
                "WARNING: Git was not found on PATH, so the cloned yt-dlp checkout "
                "could not be updated automatically."
            )

        verify_code, version_output = _run_update_command(
            [sys.executable, source_main, "--version"], timeout=30
        )
        if version_output:
            messages.append(f"yt-dlp source version: {version_output.splitlines()[-1]}")
        if verify_code == 0:
            return True, messages

        messages.append("ERROR: The cloned yt-dlp source checkout could not be executed.")
        return False, messages

    executable = find_ytdlp_executable()
    if executable:
        code, output = _run_update_command([executable, "-U"])
        messages.append(f"yt-dlp standalone updater: {executable}")
        if output:
            messages.extend(line for line in output.splitlines() if line.strip())
        if code == 0:
            command = get_ytdlp_command()
            return command is not None, messages

        if sys.platform.startswith("linux"):
            messages.append(
                "Bundled yt-dlp_linux could not update itself; the existing binary will be used."
            )
            return get_ytdlp_command() is not None, messages

        messages.append("Standalone update did not succeed; trying pip.")

    if sys.platform.startswith("linux"):
        messages.append(
            "Missing binaries/yt-dlp source checkout or binaries/yt-dlp_linux."
        )
        return False, messages

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

    ffmpeg = find_ffmpeg_executable("ffmpeg")
    ffprobe = find_ffmpeg_executable("ffprobe")
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


def probe_input_audio(src: str) -> dict:
    """Return basic information about the first audio stream in *src*."""
    features = detect_ffmpeg_features()
    ffprobe = features.get("ffprobe")
    if not ffprobe:
        return {}

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,profile,sample_rate,channels",
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
    def __init__(self, urls: list[str], opts: dict, output_queue: queue.Queue):
        super().__init__(daemon=True)
        self.urls = urls
        self.url = urls[0] if urls else ""
        self.opts = opts
        self.q = output_queue
        self.proc: Optional[subprocess.Popen] = None
        self.downloaded_files: list[str] = []

    def _log_capabilities(self) -> None:
        features = detect_ffmpeg_features()
        ffmpeg = features.get("ffmpeg")
        if not ffmpeg:
            if sys.platform.startswith("linux"):
                self.q.put(("error", "ffmpeg was not found on the Linux system PATH."))
            else:
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
        self.q.put((
            "log",
            "yt-dlp audio conversion: "
            + ("enabled" if self.opts.get("use_ytdlp_audio_conversion", True) else "disabled"),
        ))

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
            if self.opts.get("use_ytdlp_audio_conversion", True):
                audio_format = str(self.opts.get("container") or "best").lower()
                cmd += ["-x", "--audio-format", audio_format]

                # Explicitly point yt-dlp at the same FFmpeg installation used
                # by the application. This is especially useful for the bundled
                # Windows binaries while still working with PATH FFmpeg on Linux.
                ffmpeg = find_ffmpeg_executable("ffmpeg")
                if ffmpeg:
                    cmd += ["--ffmpeg-location", os.path.dirname(ffmpeg)]

                self.q.put((
                    "log",
                    f"yt-dlp audio post-processing enabled: --audio-format {audio_format}",
                ))
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

    def _copy_audio_compatible(self, source_codec: str, dst: str) -> bool:
        """Return whether an existing audio stream can be safely copied to dst."""
        codec = (source_codec or "").lower()
        extension = os.path.splitext(dst)[1].lower()

        if extension == ".mkv":
            return True
        if extension == ".webm":
            return codec in {"opus", "vorbis"}
        if extension in {".mp4", ".mov", ".m4a"}:
            return codec in {"aac", "alac", "mp3", "mp2", "ac3", "eac3", "flac"}
        if extension == ".mp3":
            return codec == "mp3"
        if extension == ".wav":
            return codec.startswith("pcm_")
        if extension == ".flac":
            return codec == "flac"
        if extension == ".opus":
            return codec == "opus"

        return False

    def _fallback_audio_codec_for_container(self, dst: str) -> Optional[str]:
        """Pick a sane encoder when stream-copy is invalid for the destination."""
        extension = os.path.splitext(dst)[1].lower()
        return {
            ".mp4": "aac",
            ".mov": "aac",
            ".m4a": "aac",
            ".mp3": "mpeg-1",
            ".wav": "lpcm",
            ".flac": "flac",
            ".opus": "opus",
            ".webm": "opus",
        }.get(extension)

    def _resolved_audio_args(
        self,
        src: str,
        dst: str,
        audio_codec: Optional[str],
        mode: str,
    ) -> list[str]:
        """Resolve 'copy' against the actual source codec and destination container."""
        if audio_codec not in (None, "copy"):
            return self._audio_args(audio_codec, mode)

        info = probe_input_audio(src)
        source_codec = str(info.get("codec_name") or "").lower()
        if source_codec and self._copy_audio_compatible(source_codec, dst):
            self.q.put(("log", f"Audio stream copy is compatible: {source_codec} -> {os.path.splitext(dst)[1].lower()}"))
            return ["-c:a", "copy"]

        fallback = self._fallback_audio_codec_for_container(dst)
        if fallback:
            shown_source = source_codec or "unknown codec"
            self.q.put((
                "log",
                f"Audio stream copy is not compatible: {shown_source} -> "
                f"{os.path.splitext(dst)[1].lower()}. Transcoding audio as {fallback} instead.",
            ))
            return self._audio_args(fallback, mode)

        # Unknown destination: preserve the user's explicit copy request and let
        # FFmpeg report any muxer limitation.
        return ["-c:a", "copy"]

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
        audio_args = self._resolved_audio_args(src, dst, audio_codec, "video")
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

    def _finalize_ytdlp_audio(self, src: str, dst: str) -> bool:
        """Move yt-dlp's already post-processed audio file to its final name."""
        src_abs = os.path.abspath(src)
        dst_abs = os.path.abspath(dst)

        if os.path.normcase(src_abs) == os.path.normcase(dst_abs):
            return os.path.isfile(dst_abs) and os.path.getsize(dst_abs) > 0

        try:
            if os.path.isfile(dst_abs):
                os.remove(dst_abs)
            os.replace(src_abs, dst_abs)
        except OSError as exc:
            self.q.put(("error", f"Could not finalize yt-dlp audio output: {exc}"))
            return False

        if not os.path.isfile(dst_abs) or os.path.getsize(dst_abs) <= 0:
            self.q.put(("error", f"yt-dlp audio output is missing or empty: {dst_abs}"))
            return False

        self.q.put(("log", f"yt-dlp audio finalized without a second FFmpeg conversion: {dst_abs}"))
        return True

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
        cmd += self._resolved_audio_args(src, dst, audio_codec, "audio")
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

    def _run_single_url(self, url: str, index: int, total: int) -> tuple[bool, str]:
        self.url = url
        self.downloaded_files = []
        out_folder = self.opts.get("outdir", os.path.expanduser("~/Downloads"))

        self.q.put(("log", f"=== Link {index}/{total}: {url} ==="))
        mode = self.opts["mode"]
        outtmpl, out_folder = self._build_outtmpl(out_folder, mode)
        self.q.put(("log", f"Output template: {outtmpl}"))

        before_download = snapshot_temp_files(out_folder)
        success = self._run_yt_dlp_subprocess(outtmpl, mode)
        if not success:
            self.q.put(("error", f"Link {index}/{total} failed; conversion was not started."))
            return False, out_folder

        candidates = unique_existing_paths(self.downloaded_files)
        snapshot_candidates = self._find_changed_intermediate_files(
            out_folder, before_download
        )
        candidates = unique_existing_paths([*candidates, *snapshot_candidates])
        candidates.sort(key=lambda path: os.path.getmtime(path))

        use_ytdlp_audio = (
            mode == "audio" and self.opts.get("use_ytdlp_audio_conversion", True)
        )
        if use_ytdlp_audio:
            target_extension = "." + str(self.opts["container"]).lower().lstrip(".")
            candidates = [
                path
                for path in candidates
                if os.path.splitext(path)[1].lower() == target_extension
            ]

        if not candidates:
            if use_ytdlp_audio:
                self.q.put((
                    "error",
                    f"Link {index}/{total}: yt-dlp did not create the requested "
                    f"{self.opts['container']} audio file.",
                ))
            else:
                self.q.put(("error", f"Link {index}/{total}: no newly downloaded intermediate file was found."))
            return False, out_folder

        successful_outputs: list[str] = []
        successful_pairs: list[tuple[str, str]] = []
        for src in candidates:
            final = build_final_path(src, self.opts["container"])
            if use_ytdlp_audio:
                self.q.put(("log", f"Finalizing yt-dlp audio: {src} -> {final}"))
                converted = self._finalize_ytdlp_audio(src, final)
            else:
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
            self.q.put(("error", f"Link {index}/{total}: no output files were created successfully."))
            return False, out_folder

        for src, final in successful_pairs:
            if os.path.isfile(final):
                self._cleanup_after_success(src, final)

        self.q.put(("log", f"Link {index}/{total}: created {len(successful_outputs)} output file(s)."))
        return True, out_folder

    def run(self) -> None:
        out_folder = self.opts.get("outdir", os.path.expanduser("~/Downloads"))
        try:
            self._log_capabilities()
            total = len(self.urls)
            successful_links = 0

            for index, url in enumerate(self.urls, start=1):
                try:
                    success, out_folder = self._run_single_url(url, index, total)
                    if success:
                        successful_links += 1
                except Exception as exc:
                    self.q.put(("error", f"Link {index}/{total} failed with an exception: {exc}"))

            failed_links = total - successful_links
            self.q.put((
                "log",
                f"Batch complete: {successful_links} succeeded, {failed_links} failed, {total} total.",
            ))
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
        self.startup_prepare_in_progress = True
        self.startup_tools_ready = False

        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="URL(s):").pack(side="left")
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
        self.status_var = tk.StringVar(value="Preparing FFmpeg / yt-dlp")
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
        self.log(
            "yt-dlp audio conversion: "
            + ("enabled" if self.settings["use_ytdlp_audio_conversion"] else "disabled")
        )
        if config_warning:
            self.log(f"WARNING: {config_warning}")
        self.on_mode_change()
        self.root.after(100, self._start_tool_preparation)
        self.root.after(150, self._process_queue)

    def _start_tool_preparation(self) -> None:
        threading.Thread(target=self._startup_prepare_thread, daemon=True).start()

    def _startup_prepare_thread(self) -> None:
        def startup_log(message: str) -> None:
            self.q.put(("log", message))

        startup_log("Preparing local FFmpeg and yt-dlp tools...")
        ffmpeg_ready = ensure_ffmpeg_ready(startup_log)

        if ffmpeg_ready:
            startup_log("Checking the cloned yt-dlp checkout for updates...")
            ytdlp_success, messages = update_ytdlp_installation()
            for message in messages:
                startup_log(message)
            ytdlp_ready = ytdlp_success and get_ytdlp_command() is not None
        else:
            startup_log("Skipping yt-dlp preparation because FFmpeg setup failed.")
            ytdlp_ready = False

        self.q.put(("startup_tools_done", ffmpeg_ready, ytdlp_ready))

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
        ytdlp_audio_var = tk.BooleanVar(
            value=self.settings["use_ytdlp_audio_conversion"]
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
        playlist_box.grid(row=2, column=1, sticky="w", pady=(0, 10))

        ttk.Checkbutton(
            content,
            text="Use yt-dlp for audio format conversion (--audio-format)",
            variable=ytdlp_audio_var,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(0, 14))

        content.columnconfigure(1, weight=1)

        buttons = ttk.Frame(content)
        buttons.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 0))

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
                "use_ytdlp_audio_conversion": bool(ytdlp_audio_var.get()),
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
            self.log(
                "yt-dlp audio conversion: "
                + ("enabled" if self.settings["use_ytdlp_audio_conversion"] else "disabled")
            )
            self.on_mode_change()
            self._close_settings()

        def reset_fields() -> None:
            backend_var.set(DEFAULT_CONFIG["encoder_backend"])
            directory_var.set(DEFAULT_CONFIG["default_download_dir"])
            playlist_var.set("Yes" if DEFAULT_CONFIG["download_playlist"] else "No")
            ytdlp_audio_var.set(DEFAULT_CONFIG["use_ytdlp_audio_conversion"])

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
            self.audio_codec_dd.configure(
                state=(
                    "disabled"
                    if self.settings.get("use_ytdlp_audio_conversion", True)
                    else "normal"
                )
            )
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

            # When enabled, yt-dlp's ExtractAudio postprocessor owns the audio
            # format conversion, so the separate FFmpeg audio-codec selector is
            # intentionally ignored for audio-only downloads.
            if self.settings.get("use_ytdlp_audio_conversion", True):
                return None

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
        if self.startup_prepare_in_progress:
            messagebox.showinfo(
                "Preparing tools",
                "FFmpeg / yt-dlp startup preparation is still running.",
            )
            return

        if not self.startup_tools_ready:
            # Re-check in case the user fixed the local toolchain after startup.
            self.startup_tools_ready = bool(
                find_ffmpeg_executable("ffmpeg")
                and find_ffmpeg_executable("ffprobe")
                and get_ytdlp_command()
            )
            if not self.startup_tools_ready:
                messagebox.showerror(
                    "Tools not ready",
                    "FFmpeg or yt-dlp is not ready. Check the startup log, fix the reported toolchain issue, and restart the app.",
                )
                return

        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Already running", "A download is already running.")
            return

        raw_urls = self.url_var.get().strip()
        urls = [item.strip() for item in raw_urls.split(";") if item.strip()]
        if not urls:
            messagebox.showwarning("No URL", "Enter at least one URL.")
            return

        unusual_urls = [
            url
            for url in urls
            if not (
                url.startswith("http://")
                or url.startswith("https://")
                or url.startswith("ytsearch:")
            )
        ]
        if unusual_urls:
            preview = "\n".join(unusual_urls[:5])
            if len(unusual_urls) > 5:
                preview += f"\n...and {len(unusual_urls) - 5} more"
            proceed = messagebox.askyesno(
                "Validate URLs",
                "Some entries do not look like HTTP(S) URLs:\n\n"
                f"{preview}\n\nProceed anyway?",
            )
            if not proceed:
                return

        outdir = self.outdir_var.get().strip() or os.path.expanduser("~/Downloads")
        try:
            os.makedirs(outdir, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Output folder error", str(exc))
            return

        if not (find_ffmpeg_executable("ffmpeg") and find_ffmpeg_executable("ffprobe")):
            messagebox.showerror(
                "ffmpeg missing",
                "The compiled FFmpeg tools are missing. Restart the app to run first-run compilation and check the build log.",
            )
            return

        if not get_ytdlp_command():
            messagebox.showerror(
                "yt-dlp missing",
                "The cloned binaries/yt-dlp checkout could not be started. Check the startup log.",
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
            "use_ytdlp_audio_conversion": self.settings["use_ytdlp_audio_conversion"],
        }

        self.status_var.set("Running")
        self.start_btn.configure(state="disabled")
        self.worker = Worker(urls, options, self.q)
        self.worker.start()
        self.log(f"Worker started with {len(urls)} link(s).")

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
                elif kind == "startup_tools_done":
                    ffmpeg_ready, ytdlp_ready = bool(item[1]), bool(item[2])
                    self.startup_prepare_in_progress = False
                    self.startup_tools_ready = ffmpeg_ready and ytdlp_ready
                    if self.startup_tools_ready:
                        self.start_btn.configure(state="normal")
                        self.status_var.set("Idle")
                        self.log("Startup tool preparation finished. FFmpeg and yt-dlp are ready.")
                    else:
                        self.start_btn.configure(state="disabled")
                        self.status_var.set("Tool setup failed")
                        if not ffmpeg_ready:
                            self.log("ERROR: FFmpeg first-run setup did not complete successfully.")
                        if not ytdlp_ready:
                            self.log("ERROR: yt-dlp source setup did not complete successfully.")
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
