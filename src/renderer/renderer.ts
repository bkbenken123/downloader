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

function initApp() {
  console.log('Initializing app...');
  
  const mode = document.getElementById('mode') as HTMLSelectElement | null;
  const container = document.getElementById('container') as HTMLSelectElement | null;
  const videoCodec = document.getElementById('videoCodec') as HTMLSelectElement | null;
  const audioCodec = document.getElementById('audioCodec') as HTMLSelectElement | null;
  const downloadBtn = document.getElementById('download') as HTMLButtonElement | null;
  const consoleEl = document.getElementById('console') as HTMLPreElement | null;
  const urlInput = document.getElementById('url') as HTMLInputElement | null;
  const downloadPathInput = document.getElementById('downloadPath') as HTMLInputElement | null;

  console.log('Elements found:', { mode, container, videoCodec, audioCodec, downloadBtn, consoleEl, urlInput, downloadPathInput });

  if (!mode || !container || !videoCodec || !audioCodec || !downloadBtn || !consoleEl || !urlInput || !downloadPathInput) {
    console.error('Required DOM elements not found');
    return;
  }

  console.log('All elements found, starting initialization');

  function logToConsole(msg: string) {
    console.log('[Console]', msg);
    if (consoleEl) {
      consoleEl.textContent += msg + '\n';
      consoleEl.scrollTop = consoleEl.scrollHeight;
    }
  }

  function fillContainers() {
    console.log('Filling containers...');
    if (!container || !mode) {
      console.error('Container or mode is null in fillContainers');
      return;
    }
    
    container.innerHTML = '';
    const list = containers[mode.value as 'video' | 'audio'];
    console.log('Container list:', list);

    for (const c of list) {
      const option = document.createElement('option');
      option.value = c;
      option.textContent = c;
      container.appendChild(option);
    }

    refreshCodecs();
  }

  function refreshCodecs() {
    console.log('Refreshing codecs...');
    if (!videoCodec || !audioCodec || !container || !mode) {
      console.error('Missing element in refreshCodecs');
      return;
    }
    
    videoCodec.innerHTML = '';
    audioCodec.innerHTML = '';

    const selected = compatibility[container.value];
    console.log('Selected compatibility:', selected);

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
    console.log('Codecs refreshed');
  }

  // Initialize UI
  console.log('Initializing UI components');
  fillContainers();
  logToConsole('✓ UI initialized');

  // Setup event listeners
  console.log('Setting up event listeners');
  mode.addEventListener('change', () => {
    console.log('Mode changed to:', mode.value);
    fillContainers();
  });
  container.addEventListener('change', () => {
    console.log('Container changed to:', container.value);
    refreshCodecs();
  });

  downloadBtn.addEventListener('click', async (e: Event) => {
    console.log('Download button clicked', e);
    e.preventDefault();
    e.stopPropagation();

    try {
      const url = urlInput.value.trim();
      console.log('URL:', url);

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

      const api = (window as any).electronAPI;
      console.log('electronAPI available:', !!api);
      if (!api || !api.startDownload) {
        console.error('electronAPI not available');
        logToConsole('ERROR: Application not properly initialized. Please restart.');
        throw new Error('electronAPI not available');
      }

      console.log('Calling electronAPI.startDownload');
      const result = await api.startDownload(data);
      console.log('Download result:', result);
      logToConsole('✓ Download completed');
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      console.error('Download failed:', error);
      logToConsole(`\n✗ Download failed: ${errorMsg}\n`);
    } finally {
      downloadBtn.disabled = false;
      downloadBtn.textContent = 'Download';
    }
  });

  // Setup console listener
  console.log('Setting up console listener');
  const api = (window as any).electronAPI;
  console.log('electronAPI:', api);
  if (api && api.onConsole) {
    try {
      console.log('Setting up onConsole listener');
      api.onConsole((msg: string) => {
        console.log('Received console message:', msg);
        logToConsole(msg);
      });
      logToConsole('✓ Ready to download');
    } catch (error) {
      console.error('Failed to setup console listener:', error);
    }
  } else {
    console.error('electronAPI not available:', { api, hasOnConsole: api && api.onConsole });
    logToConsole('⚠ electronAPI not available');
  }

  console.log('App initialization complete');
}

// Wait for DOM to be fully loaded
console.log('Document ready state:', document.readyState);
if (document.readyState === 'loading') {
  console.log('Waiting for DOMContentLoaded');
  document.addEventListener('DOMContentLoaded', () => {
    console.log('DOMContentLoaded fired');
    initApp();
  });
} else {
  console.log('DOM already loaded, initializing immediately');
  initApp();
}
