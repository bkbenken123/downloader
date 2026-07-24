"use strict";
const containers = {
    video: ['mp4', 'webm', 'mov', 'mkv'],
    audio: ['mp3', 'm4a', 'wav', 'flac']
};
const compatibility = {
    mp4: {
        video: ['default', 'h264', 'h265', 'av1'],
        audio: ['default', 'aac']
    },
    webm: {
        video: ['default', 'av1'],
        audio: ['default', 'opus']
    },
    mov: {
        video: ['default', 'h264', 'h265', 'prores422', 'prores4444'],
        audio: ['default', 'aac', 'lpcm']
    },
    mkv: {
        video: ['default', 'h264', 'h265', 'prores422', 'prores4444', 'av1'],
        audio: ['default', 'aac', 'opus', 'flac', 'lpcm']
    },
    mp3: {
        video: ['default'],
        audio: ['default']
    },
    m4a: {
        video: ['default'],
        audio: ['default', 'aac']
    },
    wav: {
        video: ['default'],
        audio: ['default', 'lpcm']
    },
    flac: {
        video: ['default'],
        audio: ['default', 'flac']
    }
};
function initApp() {
    const mode = document.getElementById('mode');
    const container = document.getElementById('container');
    const videoCodec = document.getElementById('videoCodec');
    const audioCodec = document.getElementById('audioCodec');
    const downloadBtn = document.getElementById('download');
    const consoleEl = document.getElementById('console');
    const urlInput = document.getElementById('url');
    const downloadPathInput = document.getElementById('downloadPath');
    if (!mode || !container || !videoCodec || !audioCodec || !downloadBtn || !consoleEl || !urlInput || !downloadPathInput) {
        console.error('Required DOM elements not found');
        return;
    }
    function logToConsole(msg) {
        if (consoleEl) {
            consoleEl.textContent += msg + '\n';
            consoleEl.scrollTop = consoleEl.scrollHeight;
        }
    }
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
        const selected = compatibility[container.value];
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
        videoCodec.disabled = mode.value === 'audio';
    }
    // Initialize UI
    fillContainers();
    // Setup event listeners
    mode.addEventListener('change', fillContainers);
    container.addEventListener('change', refreshCodecs);
    downloadBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        console.log('Download button clicked');
        try {
            const url = urlInput.value.trim();
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
            console.log('Starting download with data:', data);
            logToConsole('\n[Starting download...]\n');
            downloadBtn.disabled = true;
            downloadBtn.textContent = 'Downloading...';
            const api = window.electronAPI;
            if (!api || !api.startDownload) {
                console.error('electronAPI not available');
                logToConsole('ERROR: Application not properly initialized. Please restart.');
                throw new Error('electronAPI not available');
            }
            console.log('Calling electronAPI.startDownload');
            await api.startDownload(data);
            console.log('Download completed');
        }
        catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error);
            console.error('Download failed:', error);
            logToConsole(`\n✗ Download failed: ${errorMsg}\n`);
        }
        finally {
            downloadBtn.disabled = false;
            downloadBtn.textContent = 'Download';
        }
    });
    // Setup console listener
    const api = window.electronAPI;
    if (api && api.onConsole) {
        try {
            api.onConsole((msg) => {
                logToConsole(msg);
            });
            logToConsole('✓ UI initialized successfully');
        }
        catch (error) {
            console.error('Failed to setup console listener:', error);
        }
    }
    else {
        console.error('electronAPI not available');
    }
}
// Wait for DOM to be fully loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
}
else {
    initApp();
}
