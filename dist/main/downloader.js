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
        let downloadedFile = null;
        let mergedFile = null;
        const allDownloadedFiles = [];
        const yt = (0, child_process_1.spawn)(ytdlp, args);
        yt.stdout.on("data", d => {
            const output = d.toString();
            log(output);
            // Try to extract the final merged file from [Merger] line
            // Pattern: [Merger] Merging formats into "path/to/file.ext"
            const mergerMatch = output.match(/\[Merger\]\s+Merging formats into\s+"(.+)"/);
            if (mergerMatch && mergerMatch[1]) {
                mergedFile = mergerMatch[1].trim();
                log(`[INFO] Detected merged file: ${mergedFile}`);
            }
            // Extract playlist name from download finished message
            const playlistMatch = output.match(/\[download\]\s+Finished downloading playlist:\s+(.+)/);
            if (playlistMatch && playlistMatch[1]) {
                playlistName = playlistMatch[1].trim();
                log(`[INFO] Detected playlist: ${playlistName}`);
            }
            // Capture files that have already been downloaded
            // Pattern: [download] C:\path\to\file.ext has already been downloaded
            const alreadyMatch = output.match(/\[download\]\s+(.+)\s+has already been downloaded/);
            if (alreadyMatch && alreadyMatch[1]) {
                downloadedFile = alreadyMatch[1].trim();
                if (downloadedFile && !allDownloadedFiles.includes(downloadedFile)) {
                    allDownloadedFiles.push(downloadedFile);
                }
                log(`[INFO] Detected already downloaded file: ${downloadedFile}`);
            }
            // Also capture regular download destinations - use .+ to capture any characters including Unicode
            const destMatch = output.match(/\[download\]\s+Destination:\s+(.+)/);
            if (destMatch && destMatch[1]) {
                downloadedFile = destMatch[1].trim();
                if (downloadedFile && !allDownloadedFiles.includes(downloadedFile)) {
                    allDownloadedFiles.push(downloadedFile);
                }
                log(`[INFO] Detected file: ${downloadedFile}`);
            }
            // Capture individual file downloads - use .+ to capture any characters
            const fileMatch = output.match(/\[download\]\s+\d+\.\d+%.*?to\s+"(.+)"/);
            if (fileMatch && fileMatch[1]) {
                const file = fileMatch[1].trim();
                if (!allDownloadedFiles.includes(file)) {
                    allDownloadedFiles.push(file);
                }
            }
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
            // For playlists, construct the directory path and find files
            if (isPlaylist(data.url) && playlistName) {
                const playlistDir = path_1.default.join(downloadsDir, playlistName);
                if (fs_1.default.existsSync(playlistDir)) {
                    log(`[INFO] Scanning playlist directory: ${playlistDir}`);
                    convertPlaylistFiles(playlistDir, data, vEncoder, aEncoder, ffmpeg, log, resolve);
                    return;
                }
            }
            // Use merged file if available, otherwise use the last downloaded file
            let fileToConvert = mergedFile || downloadedFile;
            // If still no file, try using the first detected file
            if (!fileToConvert && allDownloadedFiles.length > 0) {
                fileToConvert = allDownloadedFiles[allDownloadedFiles.length - 1];
                log(`[INFO] Using file: ${fileToConvert}`);
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
        const supportedExts = ['mp4', 'mkv', 'webm', 'mov', 'avi', 'flv', 'mp3', 'm4a', 'wav', 'flac', 'aac', 'opus', 'ogg'];
        const mediaFiles = files.filter(file => {
            const ext = path_1.default.extname(file).toLowerCase().slice(1);
            return ext && supportedExts.includes(ext);
        });
        log(`Found ${mediaFiles.length} media file(s) in playlist`);
        if (mediaFiles.length === 0) {
            log("No media files to convert in playlist");
            resolve(true);
            return;
        }
        let converted = 0;
        let failed = 0;
        mediaFiles.forEach((fileName, index) => {
            const fullPath = path_1.default.join(playlistDir, fileName);
            log(`[${index + 1}/${mediaFiles.length}] Converting: ${fileName}`);
            convertFile(fullPath, data, vEncoder, aEncoder, ffmpegPath, log, (success) => {
                if (success) {
                    converted++;
                }
                else {
                    failed++;
                }
                // If all files are done, resolve
                if (converted + failed === mediaFiles.length) {
                    log(`\n=== Playlist Conversion Summary ===`);
                    log(`Successfully converted: ${converted}/${mediaFiles.length}`);
                    if (failed > 0) {
                        log(`Failed: ${failed}/${mediaFiles.length}`);
                    }
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
        // Check if file exists
        if (!fs_1.default.existsSync(filePath)) {
            log(`✗ File not found: ${filePath}`);
            resolve(false);
            return;
        }
        const fileName = path_1.default.basename(filePath);
        const fileNameWithoutExt = path_1.default.parse(filePath).name;
        const dirPath = path_1.default.dirname(filePath);
        const outputFile = path_1.default.join(dirPath, `${fileNameWithoutExt}_converted.${data.container}`);
        log(`Converting: ${fileName}`);
        // Build ffmpeg conversion command
        const ffmpegArgs = [
            "-i", filePath,
        ];
        // Add video codec if specified and not in audio mode
        if (data.mode !== "audio" && vEncoder) {
            ffmpegArgs.push("-c:v", vEncoder);
        }
        else if (data.mode === "audio") {
            // Skip video for audio mode
            ffmpegArgs.push("-vn");
        }
        // Add audio codec if specified
        if (aEncoder) {
            ffmpegArgs.push("-c:a", aEncoder);
        }
        ffmpegArgs.push("-y", outputFile);
        const ffmpegProcess = (0, child_process_1.spawn)(ffmpegPath, ffmpegArgs);
        ffmpegProcess.stdout.on("data", (d) => {
            const output = d.toString().trim();
            if (output) {
                log(`[FFMPEG] ${output}`);
            }
        });
        ffmpegProcess.stderr.on("data", (d) => {
            const output = d.toString().trim();
            if (output) {
                log(`[FFMPEG] ${output}`);
            }
        });
        ffmpegProcess.on("close", (code) => {
            if (code === 0) {
                log(`✓ Successfully converted: ${fileName}`);
                // Delete original file
                try {
                    fs_1.default.unlinkSync(filePath);
                    log(`✓ Deleted original file: ${fileName}`);
                    // Rename converted file to remove "_converted" suffix
                    const finalOutputFile = path_1.default.join(dirPath, `${fileNameWithoutExt}.${data.container}`);
                    fs_1.default.renameSync(outputFile, finalOutputFile);
                    log(`✓ Finalized: ${fileNameWithoutExt}.${data.container}`);
                }
                catch (err) {
                    log(`⚠ Warning: Could not clean up files: ${err}`);
                }
                resolve(true);
            }
            else {
                log(`✗ Error converting ${fileName}: FFmpeg exited with code ${code}`);
                resolve(false);
            }
        });
    }
    catch (err) {
        log(`Error during conversion: ${err}`);
        resolve(false);
    }
}
