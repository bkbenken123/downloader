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

const compatibility: any = {

    mp4: {

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

    webm: {

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

    mov: {

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
            "default",
            "aac",
            "opus",
            "flac",
            "lpcm"
        ]
    },

    m4a: {

        video: [
            "default"
        ],

        audio: [
            "default",
            "aac",
            "opus",
            "flac",
            "lpcm"
        ]
    },

    wav: {

        video: [
            "default"
        ],

        audio: [
            "default",
            "aac",
            "opus",
            "flac",
            "lpcm"
        ]
    },

    flac: {

        video: [
            "default"
        ],

        audio: [
            "default",
            "aac",
            "opus",
            "flac",
            "lpcm"
        ]
    }
};

const mode =
    document.getElementById(
        "mode"
    ) as HTMLSelectElement;

const container =
    document.getElementById(
        "container"
    ) as HTMLSelectElement;

const videoCodec =
    document.getElementById(
        "videoCodec"
    ) as HTMLSelectElement;

const audioCodec =
    document.getElementById(
        "audioCodec"
    ) as HTMLSelectElement;

function fillContainers() {

    container.innerHTML = "";

    const list =
        containers[
        mode.value as
        "video" | "audio"
        ];

    for (const c of list) {

        const option =
            document.createElement(
                "option"
            );

        option.value = c;
        option.textContent = c;

        container.appendChild(
            option
        );
    }

    refreshCodecs();
}

function refreshCodecs() {

    videoCodec.innerHTML = "";
    audioCodec.innerHTML = "";

    const selected =
        compatibility[
        container.value
        ];

    for (
        const v of selected.video
    ) {

        const option =
            document.createElement(
                "option"
            );

        option.value = v;
        option.textContent = v;

        videoCodec.appendChild(
            option
        );
    }

    for (
        const a of selected.audio
    ) {

        const option =
            document.createElement(
                "option"
            );

        option.value = a;
        option.textContent = a;

        audioCodec.appendChild(
            option
        );
    }

    if (
        mode.value === "audio"
    ) {

        videoCodec.disabled = true;

    } else {

        videoCodec.disabled = false;
    }
}

mode.onchange =
    fillContainers;

container.onchange =
    refreshCodecs;

fillContainers();

document
    .getElementById(
        "download"
    )
    ?.addEventListener(

        "click",

        async () => {

            const urlInput =
                document.getElementById(
                    "url"
                ) as HTMLInputElement;

            const data = {

                url:
                    urlInput.value,

                mode:
                    mode.value,

                container:
                    container.value,

                videoCodec:
                    videoCodec.value,

                audioCodec:
                    audioCodec.value
            };

            await (
                window as any
            )
                .electronAPI
                .startDownload(
                    data
                );
        }
    );

(
    window as any
)
    .electronAPI
    .onConsole(

        (
            msg: string
        ) => {

            const consoleEl =
                document.getElementById(
                    "console"
                );

            if (
                consoleEl
            ) {

                consoleEl.textContent +=
                    msg + "\n";

                consoleEl.scrollTop =
                    consoleEl.scrollHeight;
            }
        }
    );
