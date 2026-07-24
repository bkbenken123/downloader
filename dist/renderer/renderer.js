"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const compatibility_1 = require("../main/compatibility");
const containers = {
    video: ['mp4', 'webm', 'mov', 'mkv'],
    audio: ['mp3', 'm4a', 'wav', 'flac']
};
const mode = document.getElementById('mode');
const container = document.getElementById('container');
const videoCodec = document.getElementById('videoCodec');
const audioCodec = document.getElementById('audioCodec');
function fillContainers() {
    container.innerHTML = '';
    const list = containers[mode.value];
    for (const c of list) {
        const option = document.createElement('option');
        option.value = c;
        option.textContent = c;
        container.appendChild(option);
    }
    refreshCodecs();
}
function refreshCodecs() {
    videoCodec.innerHTML = '';
    audioCodec.innerHTML = '';
    const selected = compatibility_1.compatibility[container.value];
    if (!selected) {
        console.error(`No compatibility data for container: ${container.value}`);
        return;
    }
    for (const v of selected.video) {
        const option = document.createElement('option');
        option.value = v;
        option.textContent = v;
        videoCodec.appendChild(option);
    }
    for (const a of selected.audio) {
        const option = document.createElement('option');
        option.value = a;
        option.textContent = a;
        audioCodec.appendChild(option);
    }
    if (mode.value === 'audio') {
        videoCodec.disabled = true;
    }
    else {
        videoCodec.disabled = false;
    }
}
mode.onchange = fillContainers;
container.onchange = refreshCodecs;
fillContainers();
document.getElementById('download')?.addEventListener('click', async () => {
    const urlInput = document.getElementById('url');
    const downloadPathInput = document.getElementById('downloadPath');
    const url = urlInput.value.trim();
    // Validation
    if (!url) {
        alert('Please enter a YouTube URL');
        return;
    }
    if (!url.includes('youtube.com') && !url.includes('youtu.be')) {
        alert('Please enter a valid YouTube URL');
        return;
    }
    const data = {
        url: url,
        mode: mode.value,
        container: container.value,
        videoCodec: videoCodec.value,
        audioCodec: audioCodec.value,
        downloadPath: downloadPathInput.value.trim()
    };
    const consoleEl = document.getElementById('console');
    if (consoleEl) {
        consoleEl.textContent = '[Starting download...]\n';
    }
    await window.electronAPI.startDownload(data);
});
window.electronAPI.onConsole((msg) => {
    const consoleEl = document.getElementById('console');
    if (consoleEl) {
        consoleEl.textContent += msg + '\n';
        consoleEl.scrollTop = consoleEl.scrollHeight;
    }
});
