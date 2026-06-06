import { spawn } from "child_process";
import path from "path";
import fs from "fs";

interface DownloadRequest {
    url: string;
    mode: "video" | "audio";
    container: string;
    videoCodec: string;
    audioCodec: string;
}

function getVideoEncoder(codec: string): string | null {
    switch (codec) {
        case "h264": return "h264_amf";
        case "h265": return "hevc_amf";
        case "prores422": return "prores_ks";
        case "prores4444": return "prores_ks";
        case "av1": return "libsvtav1";
        default: return null;
    }
}

function getAudioEncoder(codec: string): string | null {
    switch (codec) {
        case "aac": return "aac";
        case "opus": return "libopus";
        case "flac": return "flac";
        case "lpcm": return "pcm_s24le";
        default: return null;
    }
}

function isPlaylist(url: string): boolean {
    return url.includes("list=");
}

export async function startDownload(
    data: DownloadRequest,
    log: (msg: string) => void
) {
    return new Promise((resolve) => {

        const ytdlp = path.join(process.cwd(), "binaries", "yt-dlp.exe");
        const ffmpeg = path.join(process.cwd(), "binaries", "ffmpeg.exe");

        const downloadsDir = path.resolve(process.cwd(), "..", "..");

        if (!fs.existsSync(downloadsDir)) {
            fs.mkdirSync(downloadsDir, { recursive: true });
        }

        let outputTemplate = "";
        let playlistName = "";

        if (isPlaylist(data.url)) {
            outputTemplate = path.join(downloadsDir, "%(playlist)s", "%(title)s.%(ext)s");
        } else {
            outputTemplate = path.join(downloadsDir, "%(title)s.%(ext)s");
        }

        let args: string[] = [
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
            } else {
                args.push("-f", "bestaudio");
            }
        } else {
            if (!requiresConversion) {
                args.push("-f", `bestvideo[ext=${data.container}]+bestaudio/best`);
            } else {
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
        const allDownloadedFiles: string[] = [];

        const yt = spawn(ytdlp, args);

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
                    downloadDir = path.dirname(downloadedFile);
                    expectedContainer = path.extname(downloadedFile).slice(1);

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
                    downloadDir = path.dirname(downloadedFile);
                    expectedContainer = path.extname(downloadedFile).slice(1);

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
                const playlistDir = path.join(downloadsDir, playlistName);

                if (fs.existsSync(playlistDir)) {
                    convertPlaylistFiles(
                        playlistDir,
                        data,
                        vEncoder,
                        aEncoder,
                        ffmpeg,
                        log,
                        resolve
                    );
                    return;
                }
            }

            let fileToConvert = mergedFile || downloadedFile;

            if (!fileToConvert && downloadDir && expectedContainer) {
                try {
                    const files = fs.readdirSync(downloadDir);
                    const mediaFile = files.find(f =>
                        path.extname(f).toLowerCase() === `.${expectedContainer}`
                    );

                    if (mediaFile) {
                        fileToConvert = path.join(downloadDir, mediaFile);
                    }
                } catch (err) {
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

            convertFile(
                fileToConvert,
                data,
                vEncoder,
                aEncoder,
                ffmpeg,
                log,
                resolve
            );
        });
    });
}

function convertPlaylistFiles(
    playlistDir: string,
    data: DownloadRequest,
    vEncoder: string | null,
    aEncoder: string | null,
    ffmpegPath: string,
    log: (msg: string) => void,
    resolve: (value: boolean) => void
) {
    try {
        const files = fs.readdirSync(playlistDir);

        const supportedExts = [
            "mp4","mkv","webm","mov","avi","flv",
            "mp3","m4a","wav","flac","aac","opus","ogg"
        ];

        const mediaFiles = files.filter(file => {
            const ext = path.extname(file).toLowerCase().slice(1);
            return supportedExts.includes(ext);
        });

        let done = 0;
        let failed = 0;

        if (mediaFiles.length === 0) {
            resolve(true);
            return;
        }

        mediaFiles.forEach((file, index) => {
            convertFile(
                path.join(playlistDir, file),
                data,
                vEncoder,
                aEncoder,
                ffmpegPath,
                log,
                (success) => {
                    success ? done++ : failed++;

                    if (done + failed === mediaFiles.length) {
                        resolve(true);
                    }
                }
            );
        });

    } catch (err) {
        log(`Error scanning playlist directory: ${err}`);
        resolve(false);
    }
}

function convertFile(
    filePath: string,
    data: DownloadRequest,
    vEncoder: string | null,
    aEncoder: string | null,
    ffmpegPath: string,
    log: (msg: string) => void,
    resolve: (value: boolean) => void
) {
    try {
        if (!fs.existsSync(filePath)) {
            resolve(false);
            return;
        }

        const dirPath = path.dirname(filePath);
        const fileNameWithoutExt = path.parse(filePath).name;

        const outputFile = path.join(
            dirPath,
            `${fileNameWithoutExt}_converted.${data.container}`
        );

        const args: string[] = ["-i", filePath];

        if (data.mode !== "audio" && vEncoder) {
            args.push("-c:v", vEncoder);
        } else if (data.mode === "audio") {
            args.push("-vn");
        }

        if (aEncoder) {
            args.push("-c:a", aEncoder);
        }

        args.push("-y", outputFile);

        const proc = spawn(ffmpegPath, args);

        proc.on("close", (code) => {
            if (code === 0) {
                try {
                    fs.unlinkSync(filePath);

                    const final = path.join(
                        dirPath,
                        `${fileNameWithoutExt}.${data.container}`
                    );

                    fs.renameSync(outputFile, final);
                    resolve(true);
                } catch {
                    resolve(true);
                }
            } else {
                resolve(false);
            }
        });

    } catch {
        resolve(false);
    }
}