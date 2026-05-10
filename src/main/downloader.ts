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

            // Find downloaded files and convert them
            findAndConvertFiles(
                downloadsDir,
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

function findAndConvertFiles(
    dir: string,
    data: DownloadRequest,
    vEncoder: string | null,
    aEncoder: string | null,
    ffmpegPath: string,
    log: (msg: string) => void,
    resolve: (value: boolean) => void
) {
    try {
        log(`Scanning directory: ${dir}`);

        // Get all files recursively
        function getAllFiles(dirPath: string, arrayOfFiles: string[] = []): string[] {
            const files = fs.readdirSync(dirPath);

            files.forEach((file) => {
                const filePath = path.join(dirPath, file);
                if (fs.statSync(filePath).isDirectory()) {
                    arrayOfFiles = getAllFiles(filePath, arrayOfFiles);
                } else {
                    arrayOfFiles.push(filePath);
                }
            });

            return arrayOfFiles;
        }

        const allFiles = getAllFiles(dir);
        log(`Found ${allFiles.length} total files`);

        // Filter for downloaded media files - get all supported formats
        const supportedExts = ['mp4', 'mkv', 'webm', 'mov', 'avi', 'flv', 'mp3', 'm4a', 'wav', 'flac', 'aac', 'opus', 'ogg'];
        
        const filesToConvert = allFiles.filter(file => {
            const ext = path.extname(file).toLowerCase().slice(1);
            // Convert any supported format if codecs need to be changed
            return ext && supportedExts.includes(ext);
        });

        log(`Found ${filesToConvert.length} file(s) to convert with new codecs`);

        if (filesToConvert.length === 0) {
            log("No files to convert found.");
            resolve(true);
            return;
        }

        let converted = 0;
        let failed = 0;

        filesToConvert.forEach((fullPath, index) => {
            const fileName = path.basename(fullPath);
            const fileNameWithoutExt = path.parse(fullPath).name;
            const dirPath = path.dirname(fullPath);
            const outputFile = path.join(
                dirPath,
                `${fileNameWithoutExt}_converted.${data.container}`
            );

            log(`[${index + 1}/${filesToConvert.length}] Converting: ${fileName}`);

            // Build ffmpeg conversion command
            const ffmpegArgs = [
                "-i", fullPath,
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
                        fs.unlinkSync(fullPath);
                        log(`✓ Deleted original file: ${fileName}`);
                        
                        // Rename converted file to remove "_converted" suffix
                        const finalOutputFile = path.join(
                            dirPath,
                            `${fileNameWithoutExt}.${data.container}`
                        );
                        fs.renameSync(outputFile, finalOutputFile);
                        log(`✓ Finalized: ${fileNameWithoutExt}.${data.container}`);
                        
                        converted++;
                    } catch (err) {
                        log(`⚠ Warning: Could not clean up files: ${err}`);
                        converted++;
                    }
                } else {
                    log(`✗ Error converting ${fileName}: FFmpeg exited with code ${code}`);
                    failed++;
                }

                // Check if all conversions are done
                if (converted + failed === filesToConvert.length) {
                    log(`\n=== Conversion Summary ===`);
                    log(`Successfully converted: ${converted}/${filesToConvert.length}`);
                    if (failed > 0) {
                        log(`Failed: ${failed}/${filesToConvert.length}`);
                    }
                    resolve(true);
                }
            });
        });
    } catch (err) {
        log(`Error during conversion: ${err}`);
        resolve(false);
    }
}
