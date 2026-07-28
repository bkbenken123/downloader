import { spawn } from 'child_process';
import path from 'path';
import os from 'os';

function getYtDlpPath(): string {
  const platform = os.platform();
  const ext = platform === 'win32' ? '.exe' : '';
  return path.join(process.cwd(), 'binaries', `yt-dlp${ext}`);
}

function getFfmpegPath(): string {
  const platform = os.platform();
  const ext = platform === 'win32' ? '.exe' : '';
  return path.join(process.cwd(), 'binaries', `ffmpeg${ext}`);
}

export function updateYtDlp(log: (msg: string) => void) {
  const ytdlp = getYtDlpPath();
  log('\n[Checking yt-dlp updates...]\n');

  const proc = spawn(ytdlp, ['-U'], { stdio: 'pipe' });

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
