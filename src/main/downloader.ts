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

function getAudioEncoder(codec: string): string | null {
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

function isPlaylist(url: string): boolean {
    return url.includes("list=");
}

export async function startDownload(
    data: DownloadRequest,
    log: (msg: string) => void
) {
    return new Promise((resolve) => {

        const ytdlp = path.join(
            process.cwd(),
            "binaries",
            "yt-dlp.exe"
        );

        const ffmpeg = path.join(
            process.cwd(),
            "binaries",
            "ffmpeg.exe"
        );

        const downloadsDir = path.resolve(
            process.cwd(),
            "..",
            ".."
        );

        if (!fs.existsSync(downloadsDir)) {
            fs.mkdirSync(downloadsDir, {
                recursive: true
            });
        }

        let outputTemplate = "";

        if (isPlaylist(data.url)) {
            outputTemplate = path.join(
                downloadsDir,
                "%(playlist)s",
                "%(title)s.%(ext)s"
            );
        } else {
            outputTemplate = path.join(
                downloadsDir,
                "%(title)s.%(ext)s"
            );
        }

        let args: string[] = [
            "--ffmpeg-location",
            ffmpeg,

            "-o",
            outputTemplate
        ];

        let requiresConversion = false;

        const vEncoder = getVideoEncoder(
            data.videoCodec
        );

        const aEncoder = getAudioEncoder(
            data.audioCodec
        );

        if (
            data.videoCodec !== "default" ||
            data.audioCodec !== "default"
        ) {
            requiresConversion = true;
        }

        if (
            data.mode === "audio"
        ) {
            if (
                data.audioCodec === "default"
            ) {
                args.push(
                    "-x",
                    "--audio-format",
                    data.container
                );
            } else {
                args.push(
                    "-f",
                    "bestaudio"
                );
            }
        } else {

            if (
                !requiresConversion
            ) {

                args.push(
                    "-f",
                    `bestvideo[ext=${data.container}]+bestaudio/best`
                );

            } else {

                args.push(
                    "-f",
                    "bestvideo+bestaudio/best"
                );

                args.push(
                    "--merge-output-format",
                    data.container
                );
            }
        }

        args.push(data.url);

        log("Starting yt-dlp...");
        log(args.join(" "));

        const yt = spawn(ytdlp, args);

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

            resolve(true);
        });
    });
}