"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.updateYtDlp = updateYtDlp;
const child_process_1 = require("child_process");
const path_1 = __importDefault(require("path"));
function updateYtDlp(log) {
    const ytdlp = path_1.default.join(process.cwd(), "binaries", "yt-dlp.exe");
    log("Checking yt-dlp updates...");
    const proc = (0, child_process_1.spawn)(ytdlp, ["-U"]);
    proc.stdout.on("data", (d) => {
        log(d.toString());
    });
    proc.stderr.on("data", (d) => {
        log(d.toString());
    });
    proc.on("close", (code) => {
        log(`yt-dlp updater exited with code ${code}`);
    });
}
