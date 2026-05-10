export const compatibility = {
    mp4: {
        video: ["default", "h264", "h265", "av1"],
        audio: ["default", "aac"]
    },

    webm: {
        video: ["default", "av1"],
        audio: ["default", "opus"]
    },

    mov: {
        video: [
            "default",
            "h264",
            "h265",
            "prores422",
            "prores4444"
        ],
        audio: ["default", "aac", "lpcm"]
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
    }
};