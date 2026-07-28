interface DownloadRequest {
    url: string;
    mode: "video" | "audio";
    container: string;
    videoCodec: string;
    audioCodec: string;
    downloadPath: string;
}
export declare function startDownload(data: DownloadRequest, log: (msg: string) => void): Promise<boolean>;
export {};
