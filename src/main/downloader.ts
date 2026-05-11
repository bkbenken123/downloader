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

        let downloadedFile: string | null = null;
        let playlistName: string | null = null;

        const yt = spawn(ytdlp, args);

        yt.stdout.on("data", d => {
            const output = d.toString();
            log(output);

            // Try to extract filename from yt-dlp output
            // Look for patterns like "[download] Destination: filename.ext"
            const destMatch = output.match(/\[download\]\s+Destination:\s+(.+)/i);
            if (destMatch && destMatch[1]) {
                downloadedFile = destMatch[1].trim();
                log(`[INFO] Detected file: ${downloadedFile}`);
            }

            // Try to extract playlist name
            const playlistMatch = output.match(/\[info\]\s+Writing playlist metadata/i);
            if (playlistMatch && isPlaylist(data.url)) {
                const playlistInfoMatch = output.match(/Downloading playlist:\s+(.+)/i);
                if (playlistInfoMatch && playlistInfoMatch[1]) {
                    playlistName = playlistInfoMatch[1].trim();
                    log(`[INFO] Detected playlist: ${playlistName}`);
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

            // If we didn't capture filename, construct it from template
            if (!downloadedFile) {
                // This is a fallback - ideally we capture it from yt-dlp output
                log("[WARNING] Could not detect exact filename from yt-dlp output");
                resolve(true);
                return;
            }

            convertFile(
                downloadedFile,
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
        // Check if file exists
        if (!fs.existsSync(filePath)) {
            log(`✗ File not found: ${filePath}`);
            resolve(false);
            return;
        }

        const fileName = path.basename(filePath);
        const fileNameWithoutExt = path.parse(filePath).name;
        const dirPath = path.dirname(filePath);
        const outputFile = path.join(
            dirPath,
            `${fileNameWithoutExt}_converted.${data.container}`
        );

        log(`Converting: ${fileName}`);

        // Build ffmpeg conversion command
        const ffmpegArgs = [
            "-i", filePath,
        ];

        // Add video codec if specified and not in audio mode
        if (data.mode !== "audio" && vEncoder) {
            ffmpegArgs.push("-c:v", vEncoder);
        } else if (data.mode === "audio") {
            // Skip video for audio mode
            ffmpegArgs.push("-vn");
        }

        // Add audio codec if specified
        if (aEncoder) {
            ffmpegArgs.push("-c:a", aEncoder);
        }

        ffmpegArgs.push("-y", outputFile);

        const ffmpegProcess = spawn(ffmpegPath, ffmpegArgs);

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
                    fs.unlinkSync(filePath);
                    log(`✓ Deleted original file: ${fileName}`);
                    
                    // Rename converted file to remove "_converted" suffix
                    const finalOutputFile = path.join(
                        dirPath,
                        `${fileNameWithoutExt}.${data.container}`
                    );
                    fs.renameSync(outputFile, finalOutputFile);
                    log(`✓ Finalized: ${fileNameWithoutExt}.${data.container}`);
                    
                } catch (err) {
                    log(`⚠ Warning: Could not clean up files: ${err}`);
                }
                
                log(`\n=== Conversion Complete ===`);
                resolve(true);
            } else {
                log(`✗ Error converting ${fileName}: FFmpeg exited with code ${code}`);
                resolve(false);
            }
        });
    } catch (err) {
        log(`Error during conversion: ${err}`);
        resolve(false);
    }
}
