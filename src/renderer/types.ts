export interface DownloadRequest {
    url: string;

    mode: "video" | "audio";

    container: string;

    videoCodec: string;

    audioCodec: string;
}