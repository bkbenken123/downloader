import { spawn } from "child_process";
import path from "path";
import fs from "fs";

interface DownloadRequest {
    url: string;
    mode: "video" | "audio";
    container: string;
    videoCodec: string;
    audioCodec: string;
    downloadPath: string;
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

        // Use custom download path if provided, otherwise use default
        let downloadsDir: string;
        if (data.downloadPath && data.downloadPath.trim() !== "") {
            downloadsDir = path.resolve(data.downloadPath);
        } else {
            downloadsDir = path.resolve(process.cwd(), "..", "..");
        }

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
                // Custom audio codec requires conversion - don't use -x
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
        let downloadDir = "";
        let expectedContainer = "";
        let truncatedBase = "";
        const allDownloadedFiles: string[] = [];

        const yt = spawn(ytdlp, args, { windowsHide: true });

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
                if (downloadedFile) {
                    downloadDir = path.dirname(downloadedFile);
                    expectedContainer = path.extname(downloadedFile).slice(1);
                    truncatedBase = path.parse(downloadedFile).name;
                    if (!allDownloadedFiles.includes(downloadedFile)) allDownloadedFiles.push(downloadedFile);
                }
            }

            const alreadyMatch =
                output.match(/\[download\]\s+(.+)\s+has already been downloaded/);
            if (alreadyMatch?.[1]) {
                downloadedFile = alreadyMatch[1].trim();
                if (downloadedFile) {
                    downloadDir = path.dirname(downloadedFile);
                    expectedContainer = path.extname(downloadedFile).slice(1);
                    truncatedBase = path.parse(downloadedFile).name;
                    if (!allDownloadedFiles.includes(downloadedFile)) allDownloadedFiles.push(downloadedFile);
                }
            }

            const fileMatch = output.match(/\[download\]\s+\d+\.\d+%.*?to\s+"(.+)"/);
            if (fileMatch?.[1]) {
                const file = fileMatch[1].trim();
                if (!allDownloadedFiles.includes(file)) allDownloadedFiles.push(file);
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
            if (!fs.existsSync(fileToConvert)) {
                log(`Detected path does not exist: ${fileToConvert}`);

                // Small delay to allow filesystem to settle
                setTimeout(() => {
                    performConversion(
                        downloadDir,
                        expectedContainer,
                        truncatedBase,
                        allDownloadedFiles,
                        data,
                        vEncoder,
                        aEncoder,
                        ffmpeg,
                        log,
                        resolve
                    );
                }, 150);

                return; // we'll continue after the timeout
            }

            // Path exists - proceed
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

function performConversion(
    downloadDir: string,
    expectedContainer: string,
    truncatedBase: string,
    allDownloadedFiles: string[],
    data: DownloadRequest,
    vEncoder: string | null,
    aEncoder: string | null,
    ffmpegPath: string,
    log: (msg: string) => void,
    resolve: (value: boolean) => void
) {
    try {
        if (downloadDir && expectedContainer) {
            log(`[INFO] Scanning ${downloadDir} for *.${expectedContainer} files (looking for ${truncatedBase})`);

            const files = fs.readdirSync(downloadDir);
            const candidates = files.filter(f => path.extname(f).toLowerCase() === `.${expectedContainer}`);

            // Normalize for comparison
            const target = (truncatedBase || "").toLowerCase();
            const asciiTarget = target.replace(/[^\x00-\x7F]/g, "");

            log(`[DEBUG] Candidates: ${candidates.join(", ")}`);

            let found: string | null = null;

            for (const c of candidates) {
                const name = path.parse(c).name.toLowerCase();

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

            let fileToConvert = "";

            if (found) {
                fileToConvert = path.join(downloadDir, found);
                log(`[INFO] Resolved actual file: ${fileToConvert}`);
            } else {
                log(`[WARNING] No matching file found in ${downloadDir}`);
                if (allDownloadedFiles.length > 0) {
                    fileToConvert = allDownloadedFiles[allDownloadedFiles.length - 1];
                    log(`[INFO] Falling back to last detected file: ${fileToConvert}`);
                }
            }

            if (!fileToConvert) {
                log("[WARNING] Could not detect downloaded file from yt-dlp output");
                resolve(true);
                return;
            }

            // proceed with conversion
            convertFile(
                fileToConvert,
                data,
                vEncoder,
                aEncoder,
                ffmpegPath,
                log,
                resolve
            );
        }
    } catch (err) {
        log(`[ERROR] Directory scan failed: ${err}`);
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
            log(`✗ File not found: ${filePath}`);
            resolve(false);
            return;
        }

        const dir = path.dirname(filePath);
        const name = path.parse(filePath).name;

        const outputFile = path.join(dir, `${name}_converted.${data.container}`);

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

        const ffmpegProcess = spawn(ffmpegPath, args, { windowsHide: true });

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
                    fs.unlinkSync(filePath);

                    const final = path.join(dir, `${name}.${data.container}`);
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
