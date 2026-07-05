import imageio_ffmpeg

# Get the path to the ffmpeg binary installed via pip
ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

import logging
import os
import threading
from urllib.parse import urlparse

import requests
import yt_dlp

from app.services.exceptions import ExtractionError, InvalidURLError
from app.services.job_store import Job, JobStatus, job_store
from app.utils.validators import is_valid_url, sanitize_filename

logger = logging.getLogger(__name__)


class VideoInfo:
    def __init__(self, title, thumbnail, duration, uploader, qualities):
        self.title = title
        self.thumbnail = thumbnail
        self.duration = duration
        self.uploader = uploader
        self.qualities = qualities

    def to_dict(self):
        return {
            "title": self.title,
            "thumbnail": self.thumbnail,
            "duration": self.duration,
            "uploader": self.uploader,
            "qualities": self.qualities,
        }


class DownloaderService:
    def __init__(self, download_dir: str, output_format: str = "mp4",
                 max_filename_length: int = 150):
        self.download_dir = download_dir
        self.output_format = output_format
        self.max_filename_length = max_filename_length

    # -- Metadata -------------------------------------------------------

    def fetch_info(self, url: str) -> VideoInfo:
        if not is_valid_url(url):
            raise InvalidURLError("The link provided is empty or not a valid URL.")

        # Clean, native options block allowing default multi-client processing hooks
        ydl_opts = {
            "quiet": True, 
            "no_warnings": True, 
            "skip_download": True,
            "ffmpeg_location": ffmpeg_path,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
            return VideoInfo(
                title=info.get("title", "Video Stream"),
                thumbnail=info.get("thumbnail"),
                duration=info.get("duration"),
                uploader=info.get("uploader", "Media Engine"),
                qualities=self._build_quality_options(info.get("formats", []) or []),
            )
        except Exception as exc:
            logger.exception("Metadata parsing failure for URL: %s", url)
            raise ExtractionError("Extraction engine error. Please double check your video link configuration.")

    @staticmethod
    def _build_quality_options(formats: list) -> list:
        """Reduce yt-dlp's raw format list to a de-duplicated list of resolutions."""
        seen_heights = set()
        options = []
        for fmt in formats:
            height = fmt.get("height")
            if not height or height in seen_heights or fmt.get("vcodec") == "none":
                continue
            seen_heights.add(height)
            options.append({"height": height, "label": f"{height}p"})

        options.sort(key=lambda item: item["height"], reverse=True)
        return options or [{"height": 0, "label": "Best available"}]

    # -- Download ---------------------------------------------------------

    def start_download(self, url: str, height: int) -> Job:
        if not is_valid_url(url):
            raise InvalidURLError("The link provided is empty or not a valid URL.")

        job = job_store.create()
        thread = threading.Thread(
            target=self._run_download, args=(job.id, url, height), daemon=True
        )
        thread.start()
        return job

    def _run_download(self, job_id: str, url: str, height) -> None:
        def progress_hook(event):
            if event.get("status") == "downloading":
                pct_str = event.get("_percent_str", "0%").strip()
                clean_pct = pct_str.replace('\x1b[0;32m', '').replace('\x1b[0m', '')
                job_store.update(job_id, progress=clean_pct)
            elif event.get("status") == "finished":
                job_store.update(job_id, progress="100%")

        format_selector = "bestvideo+bestaudio/best"
        if height and int(height) > 0:
            format_selector = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"

        out_template = os.path.join(self.download_dir, f"{job_id}.%(ext)s")
        ydl_opts = {
            "ffmpeg_location": ffmpeg_path,
            "format": format_selector,
            "outtmpl": out_template,
            "merge_output_format": self.output_format,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                final_path = ydl.prepare_filename(info)
                base, _ = os.path.splitext(final_path)
                merged_path = f"{base}.{self.output_format}"
                filename = os.path.basename(
                    merged_path if os.path.exists(merged_path) else final_path
                )

            job_store.update(
                job_id,
                status=JobStatus.DONE,
                filename=filename,
                title=sanitize_filename(info.get("title", "video"), self.max_filename_length),
            )
        except Exception as exc:
            logger.exception("Native pipeline background tracking thread failure: %s", exc)
            job_store.update(job_id, status=JobStatus.ERROR, error="Processing loop failed. Please try again.")
