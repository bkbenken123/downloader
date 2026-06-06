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
        let playlistName = "";

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
        let mergedFile: string | null = null;
        let downloadDir: string | null = null;
        let expectedContainer: string | null = null;
        const allDownloadedFiles: string[] = [];

        const yt = spawn(ytdlp, args);

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
                downloadDir = path.dirname(downloadedFile);
                expectedContainer = path.extname(downloadedFile).slice(1);
                if (downloadedFile && !allDownloadedFiles.includes(downloadedFile)) {
                    allDownloadedFiles.push(downloadedFile);
                }
                log(`[INFO] Detected already downloaded file: ${downloadedFile}`);
            }

            // Also capture regular download destinations - use .+ to capture any characters including Unicode
            const destMatch = output.match(/\[download\]\s+Destination:\s+(.+)/);
            if (destMatch && destMatch[1]) {
                downloadedFile = destMatch[1].trim();
                downloadDir = path.dirname(downloadedFile);
                expectedContainer = path.extname(downloadedFile).slice(1);
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
                const playlistDir = path.join(downloadsDir, playlistName);
                
                if (fs.existsSync(playlistDir)) {
                    log(`[INFO] Scanning playlist directory: ${playlistDir}`);
                    
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

            // Use merged file if available, otherwise use the last downloaded file
            let fileToConvert = mergedFile || downloadedFile;

            // If we have a download directory but the exact file path is truncated,
            // scan the directory for files with the expected container
            if (!fileToConvert && downloadDir && expectedContainer) {
                log(`[INFO] Scanning directory for ${expectedContainer} files: ${downloadDir}`);
                
                try {
                    const files = fs.readdirSync(downloadDir);
                    const mediaFile = files.find(f => path.extname(f).toLowerCase() === `.${expectedContainer}`);
                    
                    if (mediaFile) {
                        fileToConvert = path.join(downloadDir, mediaFile);
                        log(`[INFO] Found media file: ${fileToConvert}`);
                    }
                } catch (err) {
                    log(`[WARNING] Error scanning directory: ${err}`);
                }
            }

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
        const supportedExts = ['mp4', 'mkv', 'webm', 'mov', 'avi', 'flv', 'mp3', 'm4a', 'wav', 'flac', 'aac', 'opus', 'ogg'];
        
        const mediaFiles = files.filter(file => {
            const ext = path.extname(file).toLowerCase().slice(1);
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
            const fullPath = path.join(playlistDir, fileName);
            
            log(`[${index + 1}/${mediaFiles.length}] Converting: ${fileName}`);

            convertFile(
                fullPath,
                data,
                vEncoder,
                aEncoder,
                ffmpegPath,
                log,
                (success) => {
                    if (success) {
                        converted++;
                    } else {
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
