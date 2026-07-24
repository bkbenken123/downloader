const containers = {
  video: ['mp4', 'webm', 'mov', 'mkv'],
  audio: ['mp3', 'm4a', 'wav', 'flac']
};

const compatibility: any = {
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

let mode: HTMLSelectElement | null = null;
let container: HTMLSelectElement | null = null;
let videoCodec: HTMLSelectElement | null = null;
let audioCodec: HTMLSelectElement | null = null;
let downloadBtn: HTMLButtonElement | null = null;
let consoleEl: HTMLPreElement | null = null;
let urlInput: HTMLInputElement | null = null;
let downloadPathInput: HTMLInputElement | null = null;

function initializeElements() {
  mode = document.getElementById('mode') as HTMLSelectElement;
  container = document.getElementById('container') as HTMLSelectElement;
  videoCodec = document.getElementById('videoCodec') as HTMLSelectElement;
  audioCodec = document.getElementById('audioCodec') as HTMLSelectElement;
  downloadBtn = document.getElementById('download') as HTMLButtonElement;
  consoleEl = document.getElementById('console') as HTMLPreElement;
  urlInput = document.getElementById('url') as HTMLInputElement;
  downloadPathInput = document.getElementById('downloadPath') as HTMLInputElement;

  if (!mode || !container || !videoCodec || !audioCodec || !downloadBtn || !consoleEl) {
    console.error('Required elements not found in DOM');
    logToConsole('ERROR: Required UI elements not found. Please refresh the page.');
    return false;
  }

  return true;
}

function logToConsole(msg: string) {
  if (consoleEl) {
    consoleEl.textContent += msg + '\n';
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }
}

function fillContainers() {
  if (!container || !mode) return;

  container.innerHTML = '';
  const list = containers[mode.value as 'video' | 'audio'];

  for (const c of list) {
    const option = document.createElement('option');
    option.value = c;
    option.textContent = c;
    container.appendChild(option);
  }

  refreshCodecs();
}

function refreshCodecs() {
  if (!videoCodec || !audioCodec || !container || !mode) return;

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

function setupEventListeners() {
  if (!mode || !container || !downloadBtn) return;

  mode.addEventListener('change', fillContainers);
  container.addEventListener('change', refreshCodecs);

  downloadBtn.addEventListener('click', async () => {
    try {
      if (!urlInput || !downloadPathInput || !videoCodec || !audioCodec || !mode || !container || !downloadBtn) {
        console.error('Missing form elements');
        return;
      }

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

      if (consoleEl) {
        consoleEl.textContent = '\n[Starting download...]\n';
      }

      downloadBtn.disabled = true;
      downloadBtn.textContent = 'Downloading...';

      const api = (window as any).electronAPI;
      if (!api || !api.startDownload) {
        console.error('electronAPI not available');
        logToConsole('ERROR: Application not properly initialized. Please restart.');
        throw new Error('electronAPI not available');
      }

      await api.startDownload(data);
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      console.error('Download failed:', error);
      logToConsole(`\n❌ Download failed: ${errorMsg}\n`);
    } finally {
      if (downloadBtn) {
        downloadBtn.disabled = false;
        downloadBtn.textContent = 'Download';
      }
    }
  });
}

function setupConsoleListener() {
  const api = (window as any).electronAPI;
  if (!api || !api.onConsole) {
    console.error('electronAPI.onConsole not available');
    return;
  }

  try {
    api.onConsole((msg: string) => {
      logToConsole(msg);
    });
  } catch (error) {
    console.error('Failed to setup console listener:', error);
  }
}

// Wait for DOM to be ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    if (initializeElements()) {
      fillContainers();
      setupEventListeners();
      setupConsoleListener();
      logToConsole('✓ UI initialized successfully');
    }
  });
} else {
  if (initializeElements()) {
    fillContainers();
    setupEventListeners();
    setupConsoleListener();
    logToConsole('✓ UI initialized successfully');
  }
}
