# Link → Video Downloader

A local web application that downloads video content from a pasted URL
(YouTube, Instagram, Twitter/X, Facebook, and any site supported by
[`yt-dlp`](https://github.com/yt-dlp/yt-dlp)). Paste a link, pick a
resolution, and download the merged video+audio file — all from a browser
UI backed by a Flask server running on your own machine.

## Features

- Fetch title, thumbnail, uploader, and available resolutions before downloading
- Background downloads with live progress polling (no page reloads)
- Automatic video+audio merging via `ffmpeg`
- Automatic cleanup of old downloaded files (configurable retention window)
- Clean separation between HTTP routes, business logic, and the extraction engine
- Structured logging (rotating file handler) and a test suite

## Architecture

```
Browser (HTML/CSS/JS)
        │  fetch() calls
        ▼
Flask routes (app/routes.py)        ── HTTP layer only: parses requests,
        │                              calls the service, returns JSON
        ▼
DownloaderService (app/services/downloader.py)
        │                           ── all yt-dlp interaction lives here
        ▼
yt-dlp + ffmpeg                     ── extraction & video/audio merging
        │
        ▼
JobStore (app/services/job_store.py) ── thread-safe in-memory job state,
                                         polled by the frontend for progress
```

Each download runs on its own background thread so the HTTP request that
starts it returns immediately; the frontend polls `/api/status/<job_id>`
until the job is marked `done` or `error`.

## Project Structure

```
link-video-downloader/
├── run.py                     # entry point — run this
├── config.py                  # environment-based configuration
├── requirements.txt
├── .env.example
├── app/
│   ├── __init__.py            # application factory
│   ├── routes.py              # Flask blueprint / HTTP layer
│   ├── services/
│   │   ├── downloader.py      # yt-dlp wrapper (metadata + download)
│   │   ├── job_store.py       # thread-safe job state
│   │   ├── cleanup.py         # background file-retention sweep
│   │   └── exceptions.py      # service-layer exception types
│   ├── utils/
│   │   └── validators.py      # URL validation, filename sanitization
│   ├── static/
│   │   ├── css/style.css
│   │   └── js/main.js
│   └── templates/
│       └── index.html
├── tests/
│   └── test_app.py            # pytest suite
└── docs/
    └── Project_Report.docx    # written project report
```

## Requirements

- Python 3.9+
- [`ffmpeg`](https://ffmpeg.org/download.html) available on your system `PATH`
  (required to merge separate video and audio streams into one file)

## Setup

```bash
# 1. Clone or extract the project, then move into it
cd link-video-downloader

# 2. (Recommended) create a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) copy the environment template and adjust values
cp .env.example .env
```

## Running

```bash
python run.py
```

Then open **http://127.0.0.1:5000** in a browser.

## Running Tests

```bash
pytest -v
```

The suite covers input validation and route-level error handling without
making real network calls to third-party video platforms (kept fast and
deterministic).

## Configuration

All configuration is centralized in `config.py` and can be overridden with
environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `FLASK_ENV` | `development` | Selects `DevelopmentConfig` / `ProductionConfig` / `TestingConfig` |
| `SECRET_KEY` | dev key | Flask secret key — set a real value in production |
| `HOST` / `PORT` | `127.0.0.1` / `5000` | Bind address for the dev server |
| `FILE_RETENTION_SECONDS` | `3600` | How long a completed download stays on disk before cleanup |
| `CLEANUP_INTERVAL_SECONDS` | `900` | How often the cleanup sweep runs |

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves the web UI |
| `GET` | `/api/health` | Liveness check |
| `POST` | `/api/info` | Body: `{"url": "..."}` — returns title/thumbnail/qualities |
| `POST` | `/api/download` | Body: `{"url": "...", "height": 720}` — starts a background job, returns `job_id` |
| `GET` | `/api/status/<job_id>` | Returns job status/progress |
| `GET` | `/api/file/<job_id>` | Downloads the finished file |

## Important: Usage Notice

This tool only fetches content that is publicly reachable at a URL you
provide — it does not host, index, or promote any content. Only download
material you own, that is in the public domain, or that the rights holder
has permitted you to download. Downloading copyrighted material without
permission may violate a platform's Terms of Service or copyright law in
your jurisdiction. Use responsibly and at your own risk.

## License

MIT — see [`LICENSE`](LICENSE).
