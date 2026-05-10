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
        case "h264":
            return "h264_amf";
        case "h265":
            return "hevc_amf";
        case "prores422":
            return "prores_ks";
        case "prores4444":
            return "prores_ks";
        case "av1":
            return "libsvtav1";
        default:
            return null;
    }
}
function getAudioEncoder(codec) {
    switch (codec) {
        case "aac":
            return "aac";
        case "opus":
            return "libopus";
        case "flac":
            return "flac";
        case "lpcm":
            return "pcm_s24le";
        default:
            return null;
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
            fs_1.default.mkdirSync(downloadsDir, {
                recursive: true
            });
        }
        let outputTemplate = "";
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
        if (data.videoCodec !== "default" ||
            data.audioCodec !== "default") {
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
        const yt = (0, child_process_1.spawn)(ytdlp, args);
        yt.stdout.on("data", d => {
            log(d.toString());
        });
        yt.stderr.on("data", d => {
            log(d.toString());
        });
        yt.on("close", (code) => {
            log(`yt-dlp exited ${code}`);
            if (!requiresConversion) {
                resolve(true);
                return;
            }
            log("Starting ffmpeg conversion...");
            // Find downloaded files and convert them
            findAndConvertFiles(downloadsDir, data, vEncoder, aEncoder, ffmpeg, log, resolve);
        });
    });
}
function findAndConvertFiles(dir, data, vEncoder, aEncoder, ffmpegPath, log, resolve) {
    try {
        const files = fs_1.default.readdirSync(dir, { recursive: true });
        let converted = 0;
        let totalFiles = 0;
        // Filter for downloaded media files (not already in target format)
        const filesToConvert = files.filter(file => {
            const ext = path_1.default.extname(file).toLowerCase().slice(1);
            return ext && ext !== data.container &&
                ['mp4', 'mkv', 'webm', 'mov', 'mp3', 'm4a', 'wav', 'flac', 'webm', 'avi', 'mov'].includes(ext);
        });
        totalFiles = filesToConvert.length;
        if (totalFiles === 0) {
            log("No files to convert found.");
            resolve(true);
            return;
        }
        log(`Found ${totalFiles} file(s) to convert`);
        filesToConvert.forEach((file, index) => {
            const fullPath = path_1.default.join(dir, file);
            const fileName = path_1.default.basename(file);
            const fileNameWithoutExt = path_1.default.parse(file).name;
            const outputFile = path_1.default.join(path_1.default.dirname(fullPath), `${fileNameWithoutExt}.${data.container}`);
            log(`Converting file ${index + 1}/${totalFiles}: ${fileName}`);
            // Build ffmpeg conversion command
            const ffmpegArgs = [
                "-i", fullPath,
            ];
            // Add video codec if specified
            if (data.mode !== "audio" && vEncoder) {
                ffmpegArgs.push("-c:v", vEncoder);
            }
            // Add audio codec if specified
            if (aEncoder) {
                ffmpegArgs.push("-c:a", aEncoder);
            }
            ffmpegArgs.push("-y", outputFile);
            const ffmpegProcess = (0, child_process_1.spawn)(ffmpegPath, ffmpegArgs);
            ffmpegProcess.stdout.on("data", (d) => {
                log(d.toString());
            });
            ffmpegProcess.stderr.on("data", (d) => {
                log(d.toString());
            });
            ffmpegProcess.on("close", (code) => {
                if (code === 0) {
                    log(`Successfully converted: ${fileName}`);
                    // Delete original file
                    try {
                        fs_1.default.unlinkSync(fullPath);
                        log(`Deleted original file: ${fileName}`);
                    }
                    catch (err) {
                        log(`Warning: Could not delete original file: ${fileName}`);
                    }
                    converted++;
                }
                else {
                    log(`Error converting ${fileName}: FFmpeg exited with code ${code}`);
                }
                // If all files are done, resolve
                if (converted + (totalFiles - converted - 1) === totalFiles - 1) {
                    log(`Conversion complete. Successfully converted ${converted}/${totalFiles} files`);
                    resolve(true);
                }
            });
        });
    }
    catch (err) {
        log(`Error during conversion: ${err}`);
        resolve(false);
    }
}
