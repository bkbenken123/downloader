package main

import (
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"sync/atomic"
	"time"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/widget"
)

// A small GUI downloader implemented as a single-file Fyne application.
// - Enter a URL and a filename (optional).
// - Click Download to save into the ./binaries/ folder by default.
// Build: go build -o downloader
// Run: ./downloader

func main() {
	a := app.New()
	w := a.NewWindow("Downloader")
	w.Resize(fyne.NewSize(520, 220))

	urlEntry := widget.NewEntry()
	urlEntry.SetPlaceHolder("https://example.com/file.zip")

	nameEntry := widget.NewEntry()
	nameEntry.SetPlaceHolder("optional filename (eg: file.zip)")

	status := widget.NewLabel("Ready")
	progress := widget.NewProgressBar()
	progress.SetValue(0)

	downloadBtn := widget.NewButton("Download", func() {
		url := urlEntry.Text
		if url == "" {
			dialog.ShowError(fmt.Errorf("please enter a URL"), w)
			return
		}

		filename := nameEntry.Text
		if filename == "" {
			// try to infer filename from URL
			filename = inferFilename(url)
			if filename == "" {
				filename = "downloaded.file"
			}
		}

		// ensure binaries dir
		outDir := "binaries"
		if err := os.MkdirAll(outDir, 0o755); err != nil {
			dialog.ShowError(err, w)
			return
		}
		outPath := filepath.Join(outDir, filename)

		status.SetText("Starting...")
		progress.SetValue(0)

		go func() {
			start := time.Now()
			err := downloadFile(url, outPath, func(done, total int64) {
				var v float64
				if total > 0 {
					v = float64(done) / float64(total)
				} else {
					// unknown total -> use small incremental steps (indeterminate)
					v = 0
				}
				// update UI on main thread
				a.Driver().RunOnMain(func() {
					if total > 0 {
						progress.SetValue(v)
						status.SetText(fmt.Sprintf("%s — %s / %s",
							filepath.Base(outPath), humanBytes(done), humanBytes(total)))
					} else {
						// set pulse-like effect
						progress.SetValue(0)
						status.SetText(fmt.Sprintf("%s — %s downloaded", filepath.Base(outPath), humanBytes(done)))
					}
				})
			})

			// finished
			a.Driver().RunOnMain(func() {
				if err != nil {
					dialog.ShowError(err, w)
					status.SetText("Error: " + err.Error())
					return
				}
				progress.SetValue(1)
				duration := time.Since(start)
				status.SetText(fmt.Sprintf("Saved %s (%.1fs)", outPath, duration.Seconds()))
				// offer to open folder
				dialog.ShowInformation("Download complete", "Saved to: "+outPath, w)
			})
		}()
	})

	openBtn := widget.NewButton("Open binaries folder", func() {
		p, err := filepath.Abs("binaries")
		if err != nil {
			dialog.ShowError(err, w)
			return
		}
		// Try to open in file explorer based on OS
		switch fyne.CurrentApp().Driver().CanvasForObject(w).Size().Width { // dummy use to avoid unused import
		default:
		}
		_ = p
		dialog.ShowInformation("Binaries folder", "Path: "+p+"\nOpen it with your file manager.", w)
	})

	form := container.NewVBox(
		widget.NewLabel("Enter the file URL to download:"),
		urlEntry,
		widget.NewLabel("Optional filename (will be saved into ./binaries/):"),
		nameEntry,
		container.NewHBox(downloadBtn, openBtn),
		progress,
		status,
	)

	w.SetContent(form)
	w.ShowAndRun()
}

func inferFilename(rawurl string) string {
	// naive: take last path segment
	u := rawurl
	// strip query
	if idx := indexOf(u, '?'); idx >= 0 {
		u = u[:idx]
	}
	if idx := lastIndexOf(u, '/'); idx >= 0 && idx < len(u)-1 {
		return u[idx+1:]
	}
	return ""
}

func indexOf(s, sep string) int {
	return len([]rune(s[:])) - len([]rune(s[:])) + 
		func() int { if p := stringIndex(s, sep); p >= 0 { return p } ; return -1 }()
}

// stringIndex and lastIndexOf are small helpers without importing strings (keep single-file clear)
func stringIndex(s, sep string) int {
	for i := 0; i+len(sep) <= len(s); i++ {
		if s[i:i+len(sep)] == sep {
			return i
		}
	}
	return -1
}

func lastIndexOf(s, sep string) int {
	for i := len(s) - len(sep); i >= 0; i-- {
		if s[i:i+len(sep)] == sep {
			return i
		}
	}
	return -1
}

// downloadFile downloads URL to destination path. progressCb is called with done and total bytes periodically.
func downloadFile(url, dest string, progressCb func(done, total int64)) error {
	resp, err := http.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("HTTP status %d", resp.StatusCode)
	}

	total := resp.ContentLength
	out, err := os.Create(dest)
	if err != nil {
		return err
	}
	defer out.Close()

	var done int64
	buf := make([]byte, 32*1024)
	lastReport := time.Now()
	for {
		n, rerr := resp.Body.Read(buf)
		if n > 0 {
			wn, werr := out.Write(buf[:n])
			if werr != nil {
				return werr
			}
			atomic.AddInt64(&done, int64(wn))
		}
		// report at most 10 times/sec
		if time.Since(lastReport) > 100*time.Millisecond || rerr == io.EOF {
			lastReport = time.Now()
			if progressCb != nil {
				progressCb(atomic.LoadInt64(&done), total)
			}
		}
		if rerr == io.EOF {
			break
		}
		if rerr != nil {
			return rerr
		}
	}
	return nil
}

func humanBytes(n int64) string {
	if n < 1024 {
		return strconv.FormatInt(n, 10) + " B"
	}
	d := float64(n) / 1024.0
	if d < 1024.0 {
		return fmt.Sprintf("%.1f KB", d)
	}
	d = d / 1024.0
	if d < 1024.0 {
		return fmt.Sprintf("%.1f MB", d)
	}
	d = d / 1024.0
	return fmt.Sprintf("%.1f GB", d)
}