import imageio_ffmpeg

# Get the path to the ffmpeg binary that was just installed via pip
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

# Distributed pool of public Cobalt API instances for high-availability YouTube extraction
COBALT_API_POOL = [
    "https://api.cobalt.tools",
    "https://co.wuk.sh",
    "https://cobalt.api.v0.pw"
]

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

    def _is_youtube(self, url: str) -> bool:
        parsed = urlparse(url)
        return any(domain in parsed.netloc for domain in ["youtube.com", "youtu.be"])

    def _resolve_direct_url(self, url: str) -> str:
        parsed = urlparse(url)
        if "diskwala.com" in parsed.netloc:
            if "/app/" in parsed.path:
                file_id = parsed.path.split("/app/")[-1].strip("/")
                return f"https://www.diskwala.com/api/v1/file/download/{file_id}"
        return url

    # -- Metadata -------------------------------------------------------

    def fetch_info(self, url: str) -> VideoInfo:
        if not is_valid_url(url):
            raise InvalidURLError("The link provided is empty or not a valid URL.")

        if self._is_youtube(url):
            for base_api in COBALT_API_POOL:
                try:
                    # Cobalt standard payload schema
                    payload = {
                        "url": url,
                        "videoQuality": "720",
                        "downloadMode": "auto"
                    }
                    headers = {
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    }
                    response = requests.post(base_api, json=payload, headers=headers, timeout=5)
                    
                    if response.status_code == 200:
                        data = response.json()
                        # If Cobalt returns a streaming URL directly or picker data structures
                        if data.get("status") in ["stream", "redirect", "success"] or data.get("url"):
                            return VideoInfo(
                                title="YouTube Media Stream",
                                thumbnail=None,
                                duration=None,
                                uploader="YouTube Core Platform",
                                qualities=[{"height": 720, "label": "720p (High Quality)"}]
                            )
                except Exception as e:
                    logger.warning("Cobalt Instance %s failed metadata step: %s", base_api, e)
                    continue

        # Fallback native processing pipeline for Instagram, Facebook, etc.
        ydl_opts = {
            "quiet": True, 
            "no_warnings": True, 
            "skip_download": True,
            "ffmpeg_location": ffmpeg_path,
            "extractor_args": {"youtube": {"player_client": ["web_safari"]}},
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
            return VideoInfo(
                title=info.get("title", "video"),
                thumbnail=info.get("thumbnail"),
                duration=info.get("duration"),
                uploader=info.get("uploader"),
                qualities=self._build_quality_options(info.get("formats", []) or []),
            )
        except Exception as exc:
            logger.exception("Unexpected error extracting info for %s", url)
            raise ExtractionError("Extraction engine error. Please try alternative platform mirror links.")

    @staticmethod
    def _build_quality_options(formats: list) -> list:
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
        if self._is_youtube(url):
            for base_api in COBALT_API_POOL:
                try:
                    job_store.update(job_id, progress="Initiating bypass handshake...")
                    payload = {
                        "url": url,
                        "videoQuality": "720",
                        "downloadMode": "auto"
                    }
                    headers = {
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    }
                    res = requests.post(base_api, json=payload, headers=headers, timeout=8).json()
                    
                    stream_url = res.get("url")
                    if stream_url:
                        target_filename = f"{job_id}.mp4"
                        target_path = os.path.join(self.download_dir, target_filename)
                        
                        response = requests.get(stream_url, stream=True, timeout=60)
                        total_size = int(response.headers.get('content-length', 0))
                        
                        downloaded = 0
                        with open(target_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=131072):
                                if chunk:
                                    f.write(chunk)
                                    downloaded += len(chunk)
                                    if total_size > 0:
                                        percent = int((downloaded / total_size) * 100)
                                        job_store.update(job_id, progress=f"{percent}%")
                                    else:
                                        job_store.update(job_id, progress="Streaming file data...")
                        
                        job_store.update(
                            job_id,
                            status=JobStatus.DONE,
                            filename=target_filename,
                            title="YouTube Downloader Media"
                        )
                        return 
                except Exception as e:
                    logger.error("Cobalt instance routing down: %s", e)
                    continue

        # -- Path B: Native Pipeline For Instagram, Facebook, Twitter, etc. --
        def progress_hook(event):
            if event.get("status") == "downloading":
                job_store.update(job_id, progress=event.get("_percent_str", "0%").strip())
            elif event.get("status") == "finished":
                job_store.update(job_id, progress="100%")

        format_selector = "bestvideo+bestaudio/best"
        if height and int(height) > 0:
            format_selector = (
                f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
            )

        out_template = os.path.join(self.download_dir, f"{job_id}.%(ext)s")
        ydl_opts = {
            "ffmpeg_location": ffmpeg_path,
            "format": format_selector,
            "outtmpl": out_template,
            "merge_output_format": self.output_format,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "extractor_args": {"youtube": {"player_client": ["web_safari"]}},
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
            job_store.update(job_id, status=JobStatus.ERROR, error="Extraction error. Check system configuration.")
