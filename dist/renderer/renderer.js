"use strict";
const containers = {
    video: [
        "mp4",
        "webm",
        "mov",
        "mkv"
    ],
    audio: [
        "mp3",
        "m4a",
        "wav",
        "flac"
    ]
};
const compatibility = {
    mp4: {
        video: [
            "default",
            "h264",
            "h265",
            "av1"
        ],
        audio: [
            "default",
            "aac"
        ]
    },
    webm: {
        video: [
            "default",
            "av1"
        ],
        audio: [
            "default",
            "opus"
        ]
    },
    mov: {
        video: [
            "default",
            "h264",
            "h265",
            "prores422",
            "prores4444"
        ],
        audio: [
            "default",
            "aac",
            "lpcm"
        ]
    },
    mkv: {
        video: [
            "default",
            "h264",
            "h265",
            "prores422",
            "prores4444",
            "av1"
        ],
        audio: [
            "default",
            "aac",
            "opus",
            "flac",
            "lpcm"
        ]
    },
    mp3: {
        video: [
            "default"
        ],
        audio: [
            "default"
        ]
    },
    m4a: {
        video: [
            "default"
        ],
        audio: [
            "default",
            "aac"
        ]
    },
    wav: {
        video: [
            "default"
        ],
        audio: [
            "default",
            "lpcm"
        ]
    },
    flac: {
        video: [
            "default"
        ],
        audio: [
            "default",
            "flac"
        ]
    }
};
const mode = document.getElementById("mode");
const container = document.getElementById("container");
const videoCodec = document.getElementById("videoCodec");
const audioCodec = document.getElementById("audioCodec");
function fillContainers() {
    container.innerHTML = "";
    const list = containers[mode.value];
    for (const c of list) {
        const option = document.createElement("option");
        option.value = c;
        option.textContent = c;
        container.appendChild(option);
    }
    refreshCodecs();
}
function refreshCodecs() {
    videoCodec.innerHTML = "";
    audioCodec.innerHTML = "";
    const selected = compatibility[container.value];
    for (const v of selected.video) {
        const option = document.createElement("option");
        option.value = v;
        option.textContent = v;
        videoCodec.appendChild(option);
    }
    for (const a of selected.audio) {
        const option = document.createElement("option");
        option.value = a;
        option.textContent = a;
        audioCodec.appendChild(option);
    }
    if (mode.value === "audio") {
        videoCodec.disabled = true;
    }
    else {
        videoCodec.disabled = false;
    }
}
mode.onchange =
    fillContainers;
container.onchange =
    refreshCodecs;
fillContainers();
document
    .getElementById("download")
    ?.addEventListener("click", async () => {
    const urlInput = document.getElementById("url");
    const downloadPathInput = document.getElementById("downloadPath");
    const data = {
        url: urlInput.value,
        mode: mode.value,
        container: container.value,
        videoCodec: videoCodec.value,
        audioCodec: audioCodec.value,
        downloadPath: downloadPathInput.value
    };
    await window
        .electronAPI
        .startDownload(data);
});
window
    .electronAPI
    .onConsole((msg) => {
    const consoleEl = document.getElementById("console");
    if (consoleEl) {
        consoleEl.textContent +=
            msg + "\n";
        consoleEl.scrollTop =
            consoleEl.scrollHeight;
    }
});
