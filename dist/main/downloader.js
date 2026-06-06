"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.startDownload = startDownload;
const child_process_1 = require("child_process");
const path_1 = __importDefault(require("path"));
const fs_1 = __importDefault(require("fs"));
function getVideoEncoder(codec) {
    switch (codec) {
        case "h264": return "h264_amf";
        case "h265": return "hevc_amf";
        case "prores422": return "prores_ks";
        case "prores4444": return "prores_ks";
        case "av1": return "libsvtav1";
        default: return null;
    }
}
function getAudioEncoder(codec) {
    switch (codec) {
        case "aac": return "aac";
        case "opus": return "libopus";
        case "flac": return "flac";
        case "lpcm": return "pcm_s24le";
        default: return null;
    }
}
function isPlaylist(url) {
    return url.includes("list=");
}
async function startDownload(data, log) {
    return new Promise((resolve) => {
        const ytdlp = path_1.default.join(process.cwd(), "binaries", "yt-dlp.exe");
        const ffmpeg = path_1.default.join(process.cwd(), "binaries", "ffmpeg.exe");
        const downloadsDir = path_1.default.resolve(process.cwd(), "..", "..");
        if (!fs_1.default.existsSync(downloadsDir)) {
            fs_1.default.mkdirSync(downloadsDir, { recursive: true });
        }
        let outputTemplate = "";
        let playlistName = "";
        if (isPlaylist(data.url)) {
            outputTemplate = path_1.default.join(downloadsDir, "%(playlist)s", "%(title)s.%(ext)s");
        }
        else {
            outputTemplate = path_1.default.join(downloadsDir, "%(title)s.%(ext)s");
        }
        let args = [
            "--ffmpeg-location",
            ffmpeg,
            "-o",
            outputTemplate
        ];
        let requiresConversion = false;
        const vEncoder = getVideoEncoder(data.videoCodec);
        const aEncoder = getAudioEncoder(data.audioCodec);
        if (data.videoCodec !== "default" || data.audioCodec !== "default") {
            requiresConversion = true;
        }
        if (data.mode === "audio") {
            if (data.audioCodec === "default") {
                args.push("-x", "--audio-format", data.container);
            }
            else {
                args.push("-f", "bestaudio");
            }
        }
        else {
            if (!requiresConversion) {
                args.push("-f", `bestvideo[ext=${data.container}]+bestaudio/best`);
            }
            else {
                args.push("-f", "bestvideo+bestaudio/best");
                args.push("--merge-output-format", data.container);
            }
        }
        args.push(data.url);
        log("Starting yt-dlp...");
        log(args.join(" "));
        let downloadedFile = "";
        let mergedFile = "";
        let downloadDir = "";
        let expectedContainer = "";
        const allDownloadedFiles = [];
        const yt = (0, child_process_1.spawn)(ytdlp, args);
        yt.stdout.on("data", d => {
            const output = d.toString();
            log(output);
            const mergerMatch = output.match(/\[Merger\]\s+Merging formats into\s+"(.+)"/);
            if (mergerMatch?.[1]) {
                mergedFile = mergerMatch[1].trim();
                log(`[INFO] Detected merged file: ${mergedFile}`);
            }
            const playlistMatch = output.match(/\[download\]\s+Finished downloading playlist:\s+(.+)/);
            if (playlistMatch?.[1]) {
                playlistName = playlistMatch[1].trim();
                log(`[INFO] Detected playlist: ${playlistName}`);
            }
            const alreadyMatch = output.match(/\[download\]\s+(.+)\s+has already been downloaded/);
            if (alreadyMatch?.[1]) {
                downloadedFile = alreadyMatch[1].trim();
                if (downloadedFile) {
                    downloadDir = path_1.default.dirname(downloadedFile);
                    expectedContainer = path_1.default.extname(downloadedFile).slice(1);
                    if (!allDownloadedFiles.includes(downloadedFile)) {
                        allDownloadedFiles.push(downloadedFile);
                    }
                }
                log(`[INFO] Detected already downloaded file: ${downloadedFile}`);
            }
            const destMatch = output.match(/\[download\]\s+Destination:\s+(.+)/);
            if (destMatch?.[1]) {
                downloadedFile = destMatch[1].trim();
                if (downloadedFile) {
                    downloadDir = path_1.default.dirname(downloadedFile);
                    expectedContainer = path_1.default.extname(downloadedFile).slice(1);
                    if (!allDownloadedFiles.includes(downloadedFile)) {
                        allDownloadedFiles.push(downloadedFile);
                    }
                }
                log(`[INFO] Detected file: ${downloadedFile}`);
            }
        });
        yt.stderr.on("data", d => {
            log(d.toString());
        });
        yt.on("close", () => {
            if (!requiresConversion) {
                resolve(true);
                return;
            }
            log("Starting ffmpeg conversion...");
            if (isPlaylist(data.url) && playlistName) {
                const playlistDir = path_1.default.join(downloadsDir, playlistName);
                if (fs_1.default.existsSync(playlistDir)) {
                    convertPlaylistFiles(playlistDir, data, vEncoder, aEncoder, ffmpeg, log, resolve);
                    return;
                }
            }
            let fileToConvert = mergedFile || downloadedFile;
            if (!fileToConvert && downloadDir && expectedContainer) {
                try {
                    const files = fs_1.default.readdirSync(downloadDir);
                    const mediaFile = files.find(f => path_1.default.extname(f).toLowerCase() === `.${expectedContainer}`);
                    if (mediaFile) {
                        fileToConvert = path_1.default.join(downloadDir, mediaFile);
                    }
                }
                catch (err) {
                    log(`[WARNING] Error scanning directory: ${err}`);
                }
            }
            if (!fileToConvert && allDownloadedFiles.length > 0) {
                fileToConvert = allDownloadedFiles[allDownloadedFiles.length - 1];
            }
            if (!fileToConvert) {
                log("[WARNING] Could not detect downloaded file from yt-dlp output");
                resolve(true);
                return;
            }
            convertFile(fileToConvert, data, vEncoder, aEncoder, ffmpeg, log, resolve);
        });
    });
}
function convertPlaylistFiles(playlistDir, data, vEncoder, aEncoder, ffmpegPath, log, resolve) {
    try {
        const files = fs_1.default.readdirSync(playlistDir);
        const supportedExts = [
            "mp4", "mkv", "webm", "mov", "avi", "flv",
            "mp3", "m4a", "wav", "flac", "aac", "opus", "ogg"
        ];
        const mediaFiles = files.filter(file => {
            const ext = path_1.default.extname(file).toLowerCase().slice(1);
            return supportedExts.includes(ext);
        });
        let done = 0;
        let failed = 0;
        if (mediaFiles.length === 0) {
            resolve(true);
            return;
        }
        mediaFiles.forEach((file, index) => {
            convertFile(path_1.default.join(playlistDir, file), data, vEncoder, aEncoder, ffmpegPath, log, (success) => {
                success ? done++ : failed++;
                if (done + failed === mediaFiles.length) {
                    resolve(true);
                }
            });
        });
    }
    catch (err) {
        log(`Error scanning playlist directory: ${err}`);
        resolve(false);
    }
}
function convertFile(filePath, data, vEncoder, aEncoder, ffmpegPath, log, resolve) {
    try {
        if (!fs_1.default.existsSync(filePath)) {
            resolve(false);
            return;
        }
        const dirPath = path_1.default.dirname(filePath);
        const fileNameWithoutExt = path_1.default.parse(filePath).name;
        const outputFile = path_1.default.join(dirPath, `${fileNameWithoutExt}_converted.${data.container}`);
        const args = ["-i", filePath];
        if (data.mode !== "audio" && vEncoder) {
            args.push("-c:v", vEncoder);
        }
        else if (data.mode === "audio") {
            args.push("-vn");
        }
        if (aEncoder) {
            args.push("-c:a", aEncoder);
        }
        args.push("-y", outputFile);
        const proc = (0, child_process_1.spawn)(ffmpegPath, args);
        proc.on("close", (code) => {
            if (code === 0) {
                try {
                    fs_1.default.unlinkSync(filePath);
                    const final = path_1.default.join(dirPath, `${fileNameWithoutExt}.${data.container}`);
                    fs_1.default.renameSync(outputFile, final);
                    resolve(true);
                }
                catch {
                    resolve(true);
                }
            }
            else {
                resolve(false);
            }
        });
    }
    catch {
        resolve(false);
    }
}
