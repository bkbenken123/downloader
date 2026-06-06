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
        // Use custom download path if provided, otherwise use default
        let downloadsDir;
        if (data.downloadPath && data.downloadPath.trim() !== "") {
            downloadsDir = path_1.default.resolve(data.downloadPath);
        }
        else {
            downloadsDir = path_1.default.resolve(process.cwd(), "..", "..");
        }
        if (!fs_1.default.existsSync(downloadsDir)) {
            fs_1.default.mkdirSync(downloadsDir, { recursive: true });
        }
        const outputTemplate = isPlaylist(data.url)
            ? path_1.default.join(downloadsDir, "%(playlist)s", "%(title)s.%(ext)s")
            : path_1.default.join(downloadsDir, "%(title)s.%(ext)s");
        const args = [
            "--ffmpeg-location",
            ffmpeg,
            "-o",
            outputTemplate
        ];
        const vEncoder = getVideoEncoder(data.videoCodec);
        const aEncoder = getAudioEncoder(data.audioCodec);
        const requiresConversion = data.videoCodec !== "default" ||
            data.audioCodec !== "default";
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
        let playlistName = "";
        let downloadDir = "";
        let expectedContainer = "";
        let truncatedBase = "";
        const allDownloadedFiles = [];
        const yt = (0, child_process_1.spawn)(ytdlp, args, { windowsHide: true });
        yt.stdout.on("data", (d) => {
            const output = d.toString();
            log(output);
            const playlistMatch = output.match(/\[download\]\s+Finished downloading playlist:\s+(.+)/);
            if (playlistMatch?.[1]) {
                playlistName = playlistMatch[1].trim();
            }
            const destMatch = output.match(/\[download\]\s+Destination:\s+(.+)/);
            if (destMatch?.[1]) {
                downloadedFile = destMatch[1].trim();
                if (downloadedFile) {
                    downloadDir = path_1.default.dirname(downloadedFile);
                    expectedContainer = path_1.default.extname(downloadedFile).slice(1);
                    truncatedBase = path_1.default.parse(downloadedFile).name;
                    if (!allDownloadedFiles.includes(downloadedFile))
                        allDownloadedFiles.push(downloadedFile);
                }
            }
            const alreadyMatch = output.match(/\[download\]\s+(.+)\s+has already been downloaded/);
            if (alreadyMatch?.[1]) {
                downloadedFile = alreadyMatch[1].trim();
                if (downloadedFile) {
                    downloadDir = path_1.default.dirname(downloadedFile);
                    expectedContainer = path_1.default.extname(downloadedFile).slice(1);
                    truncatedBase = path_1.default.parse(downloadedFile).name;
                    if (!allDownloadedFiles.includes(downloadedFile))
                        allDownloadedFiles.push(downloadedFile);
                }
            }
            const fileMatch = output.match(/\[download\]\s+\d+\.\d+%.*?to\s+"(.+)"/);
            if (fileMatch?.[1]) {
                const file = fileMatch[1].trim();
                if (!allDownloadedFiles.includes(file))
                    allDownloadedFiles.push(file);
            }
        });
        yt.stderr.on("data", (d) => {
            log(d.toString());
        });
        yt.on("error", (err) => {
            log(`yt-dlp error: ${err.message}`);
            resolve(false);
        });
        yt.on("close", (code) => {
            log(`yt-dlp exited with code ${code}`);
            if (!requiresConversion) {
                resolve(true);
                return;
            }
            log("Starting ffmpeg conversion...");
            if (!downloadedFile) {
                log("❌ No file detected from yt-dlp output");
                resolve(true);
                return;
            }
            let fileToConvert = downloadedFile;
            // If path doesn't exist, attempt a smarter directory scan
            if (!fs_1.default.existsSync(fileToConvert)) {
                log(`Detected path does not exist: ${fileToConvert}`);
                // Small delay to allow filesystem to settle
                setTimeout(() => {
                    try {
                        if (downloadDir && expectedContainer) {
                            log(`[INFO] Scanning ${downloadDir} for *.${expectedContainer} files (looking for ${truncatedBase})`);
                            const files = fs_1.default.readdirSync(downloadDir);
                            const candidates = files.filter(f => path_1.default.extname(f).toLowerCase() === `.${expectedContainer}`);
                            // Normalize for comparison
                            const target = (truncatedBase || "").toLowerCase();
                            const asciiTarget = target.replace(/[^\x00-\x7F]/g, "");
                            log(`[DEBUG] Candidates: ${candidates.join(", ")}`);
                            let found = null;
                            for (const c of candidates) {
                                const name = path_1.default.parse(c).name.toLowerCase();
                                // Direct substring match
                                if (target && name.includes(target)) {
                                    found = c;
                                    break;
                                }
                                // ASCII fallback: match ascii portion of truncated base
                                if (asciiTarget && name.includes(asciiTarget)) {
                                    found = c;
                                    break;
                                }
                                // If truncated base is short, try startsWith
                                if (target && target.length <= 4 && name.startsWith(target)) {
                                    found = c;
                                    break;
                                }
                            }
                            if (found) {
                                fileToConvert = path_1.default.join(downloadDir, found);
                                log(`[INFO] Resolved actual file: ${fileToConvert}`);
                            }
                            else {
                                log(`[WARNING] No matching file found in ${downloadDir}`);
                                if (allDownloadedFiles.length > 0) {
                                    fileToConvert = allDownloadedFiles[allDownloadedFiles.length - 1];
                                    log(`[INFO] Falling back to last detected file: ${fileToConvert}`);
                                }
                            }
                        }
                    }
                    catch (err) {
                        log(`[ERROR] Directory scan failed: ${err}`);
                    }
                    if (!fileToConvert) {
                        log("[WARNING] Could not detect downloaded file from yt-dlp output");
                        resolve(true);
                        return;
                    }
                    // proceed with conversion
                    convertFile(fileToConvert, data, vEncoder, aEncoder, ffmpeg, log, resolve);
                }, 150);
                return; // we'll continue after the timeout
            }
            // Path exists - proceed
            convertFile(fileToConvert, data, vEncoder, aEncoder, ffmpeg, log, resolve);
        });
    });
}
function convertFile(filePath, data, vEncoder, aEncoder, ffmpegPath, log, resolve) {
    try {
        if (!fs_1.default.existsSync(filePath)) {
            log(`✗ File not found: ${filePath}`);
            resolve(false);
            return;
        }
        const dir = path_1.default.dirname(filePath);
        const name = path_1.default.parse(filePath).name;
        const outputFile = path_1.default.join(dir, `${name}_converted.${data.container}`);
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
        log(`Running ffmpeg: ${args.join(" ")}`);
        const ffmpegProcess = (0, child_process_1.spawn)(ffmpegPath, args, { windowsHide: true });
        // timeout to avoid hanging
        const timeout = setTimeout(() => {
            log("✗ FFmpeg timeout reached, killing process");
            ffmpegProcess.kill("SIGKILL");
            resolve(false);
        }, 10 * 60 * 1000);
        ffmpegProcess.on("error", (err) => {
            clearTimeout(timeout);
            log(`✗ FFmpeg failed: ${err.message}`);
            resolve(false);
        });
        ffmpegProcess.stderr.on("data", (d) => {
            log(`[FFMPEG] ${d.toString()}`);
        });
        ffmpegProcess.on("close", (code) => {
            clearTimeout(timeout);
            if (code === 0) {
                try {
                    fs_1.default.unlinkSync(filePath);
                    const final = path_1.default.join(dir, `${name}.${data.container}`);
                    fs_1.default.renameSync(outputFile, final);
                    log(`✓ Converted: ${final}`);
                    resolve(true);
                }
                catch (err) {
                    log(`⚠ Cleanup error: ${err}`);
                    resolve(true);
                }
            }
            else {
                log(`✗ FFmpeg failed with code ${code}`);
                resolve(false);
            }
        });
    }
    catch (err) {
        log(`convertFile error: ${err}`);
        resolve(false);
    }
}
