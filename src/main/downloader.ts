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
    return new Promise<boolean>((resolve) => {

        const ytdlp = path.join(process.cwd(), "binaries", "yt-dlp.exe");
        const ffmpeg = path.join(process.cwd(), "binaries", "ffmpeg.exe");

        const downloadsDir = path.resolve(process.cwd(), "..", "..");

        if (!fs.existsSync(downloadsDir)) {
            fs.mkdirSync(downloadsDir, { recursive: true });
        }

        const outputTemplate = isPlaylist(data.url)
            ? path.join(downloadsDir, "%(playlist)s", "%(title)s.%(ext)s")
            : path.join(downloadsDir, "%(title)s.%(ext)s");

        const args: string[] = [
            "--ffmpeg-location",
            ffmpeg,
            "-o",
            outputTemplate
        ];

        const vEncoder = getVideoEncoder(data.videoCodec);
        const aEncoder = getAudioEncoder(data.audioCodec);

        const requiresConversion =
            data.videoCodec !== "default" ||
            data.audioCodec !== "default";

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
        let playlistName = "";

        const yt = spawn(ytdlp, args, {
            windowsHide: true
        });

        yt.stdout.on("data", (d) => {
            const output = d.toString();
            log(output);

            const playlistMatch =
                output.match(/\[download\]\s+Finished downloading playlist:\s+(.+)/);
            if (playlistMatch?.[1]) {
                playlistName = playlistMatch[1].trim();
            }

            const destMatch =
                output.match(/\[download\]\s+Destination:\s+(.+)/);
            if (destMatch?.[1]) {
                downloadedFile = destMatch[1].trim();
            }

            const alreadyMatch =
                output.match(/\[download\]\s+(.+)\s+has already been downloaded/);
            if (alreadyMatch?.[1]) {
                downloadedFile = alreadyMatch[1].trim();
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

            const fileToConvert = downloadedFile;

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
            log(`✗ File not found: ${filePath}`);
            resolve(false);
            return;
        }

        const dir = path.dirname(filePath);
        const name = path.parse(filePath).name;

        const outputFile = path.join(
            dir,
            `${name}_converted.${data.container}`
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

        log(`Running ffmpeg: ${args.join(" ")}`);

        const ffmpegProcess = spawn(ffmpegPath, args, {
            windowsHide: true
        });

        // 🔥 IMPORTANT: prevent hanging forever
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
                    fs.unlinkSync(filePath);

                    const final = path.join(
                        dir,
                        `${name}.${data.container}`
                    );

                    fs.renameSync(outputFile, final);

                    log(`✓ Converted: ${final}`);
                    resolve(true);
                } catch (err) {
                    log(`⚠ Cleanup error: ${err}`);
                    resolve(true);
                }
            } else {
                log(`✗ FFmpeg failed with code ${code}`);
                resolve(false);
            }
        });

    } catch (err) {
        log(`convertFile error: ${err}`);
        resolve(false);
    }
}