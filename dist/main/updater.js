"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.updateYtDlp = updateYtDlp;
const child_process_1 = require("child_process");
const path_1 = __importDefault(require("path"));
const os_1 = __importDefault(require("os"));
function getYtDlpPath() {
    const platform = os_1.default.platform();
    const ext = platform === 'win32' ? '.exe' : '';
    return path_1.default.join(process.cwd(), 'binaries', `yt-dlp${ext}`);
}
function getFfmpegPath() {
    const platform = os_1.default.platform();
    const ext = platform === 'win32' ? '.exe' : '';
    return path_1.default.join(process.cwd(), 'binaries', `ffmpeg${ext}`);
}
function updateYtDlp(log) {
    const ytdlp = getYtDlpPath();
    log('\n[Checking yt-dlp updates...]\n');
    const proc = (0, child_process_1.spawn)(ytdlp, ['-U'], { stdio: 'pipe' });
    proc.stdout?.on('data', (d) => {
        log(d.toString());
    });
    proc.stderr?.on('data', (d) => {
        log(d.toString());
    });
    proc.on('error', (err) => {
        log(`\n⚠ yt-dlp update check failed: ${err.message}\n`);
    });
    proc.on('close', (code) => {
        log(`\n[yt-dlp updater exited with code ${code}]\n`);
    });
}
