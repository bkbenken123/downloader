import { compatibility } from '../main/compatibility';

const containers = {
  video: ['mp4', 'webm', 'mov', 'mkv'],
  audio: ['mp3', 'm4a', 'wav', 'flac']
};

const mode = document.getElementById('mode') as HTMLSelectElement;
const container = document.getElementById('container') as HTMLSelectElement;
const videoCodec = document.getElementById('videoCodec') as HTMLSelectElement;
const audioCodec = document.getElementById('audioCodec') as HTMLSelectElement;

function fillContainers() {
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
  videoCodec.innerHTML = '';
  audioCodec.innerHTML = '';

  const selected = (compatibility as any)[container.value];

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
  } else {
    videoCodec.disabled = false;
  }
}

mode.onchange = fillContainers;
container.onchange = refreshCodecs;

fillContainers();

document.getElementById('download')?.addEventListener('click', async () => {
  const urlInput = document.getElementById('url') as HTMLInputElement;
  const downloadPathInput = document.getElementById('downloadPath') as HTMLInputElement;

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

  await (window as any).electronAPI.startDownload(data);
});

(window as any).electronAPI.onConsole((msg: string) => {
  const consoleEl = document.getElementById('console');
  if (consoleEl) {
    consoleEl.textContent += msg + '\n';
    consoleEl.scrollTop = consoleEl.scrollHeight;
  }
});
