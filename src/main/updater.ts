import {
    spawn
} from "child_process";

import path from "path";

export function updateYtDlp(

    log: (msg: string) => void

) {

    const ytdlp = path.join(

        process.cwd(),
        "binaries",
        "yt-dlp.exe"
    );

    log("Checking yt-dlp updates...");

    const proc = spawn(

        ytdlp,

        ["-U"]
    );

    proc.stdout.on(

        "data",

        (d) => {

            log(
                d.toString()
            );
        }
    );

    proc.stderr.on(

        "data",

        (d) => {

            log(
                d.toString()
            );
        }
    );

    proc.on(

        "close",

        (code) => {

            log(
                `yt-dlp updater exited with code ${code}`
            );
        }
    );
}