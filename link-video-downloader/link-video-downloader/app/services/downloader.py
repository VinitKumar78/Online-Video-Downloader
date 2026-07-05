import imageio_ffmpeg

# Get the path to the ffmpeg binary that was just installed via pip
ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

import logging
import os
import threading
from urllib.parse import urlparse, parse_qs

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

    def _is_youtube(self, url: str) -> bool:
        parsed = urlparse(url)
        return any(domain in parsed.netloc for domain in ["youtube.com", "youtu.be"])

    def _get_youtube_id(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc == 'youtu.be':
            return parsed.path.strip('/')
        if '/shorts/' in parsed.path:
            return parsed.path.split('/shorts/')[-1].split('?')[0]
        if '/live/' in parsed.path:
            return parsed.path.split('/live/')[-1].split('?')[0]
        query = parse_qs(parsed.query)
        return query.get('v', [None])[0] or parsed.path.split('/')[-1]

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

        # BYPASS FOR YOUTUBE: Use an open-source mirror API to dodge cloud server blocks
        if self._is_youtube(url):
            video_id = self._get_youtube_id(url)
            try:
                # Using a resilient public Invidious instances aggregator payload
                api_url = f"https://invidious.nerdvpn.de/api/v1/videos/{video_id}"
                response = requests.get(api_url, timeout=7)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Map format streams safely
                    qualities = []
                    seen_heights = set()
                    for fmt in data.get("formatStreams", []):
                        height = fmt.get("height")
                        if height and height not in seen_heights:
                            seen_heights.add(height)
                            qualities.append({"height": height, "label": f"{height}p"})
                    
                    if not qualities:
                        qualities = [{"height": 720, "label": "720p (Auto)"}]

                    return VideoInfo(
                        title=data.get("title", "YouTube Video"),
                        thumbnail=data.get("videoThumbnails", [{}])[0].get("url", ""),
                        duration=data.get("lengthSeconds"),
                        uploader=data.get("author", "YouTube Creator"),
                        qualities=qualities
                    )
            except Exception as e:
                logger.error("Bypass API failed, trying raw engine: %s", e)

        # Non-YouTube or Fallback native path
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
            raise ExtractionError("Server data restriction active. Try another platform link or try again later.")

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
        # Check if we should use the cloud streaming bypass for YouTube
        if self._is_youtube(url):
            video_id = self._get_youtube_id(url)
            try:
                job_store.update(job_id, progress="Processing backend pipeline...")
                api_url = f"https://invidious.nerdvpn.de/api/v1/videos/{video_id}"
                res = requests.get(api_url, timeout=10).json()
                
                # Try to grab the target quality stream URL or pick the first stable link
                stream_url = None
                for fmt in res.get("formatStreams", []):
                    if str(fmt.get("height")) == str(height):
                        stream_url = fmt.get("url")
                        break
                if not stream_url and res.get("formatStreams"):
                    stream_url = res["formatStreams"][0].get("url")
                
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
                                    job_store.update(job_id, progress="Downloading...")
                    
                    job_store.update(
                        job_id,
                        status=JobStatus.DONE,
                        filename=target_filename,
                        title=sanitize_filename(res.get("title", "video"), self.max_filename_length)
                    )
                    return
            except Exception as e:
                logger.error("Bypass download route failed: %s", e)

        # -- Path B: Standard Native Execution (For Instagram, FB, Twitter, etc.) --
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
            job_store.update(job_id, status=JobStatus.ERROR, error="Extraction rate-limit hit. Please try another video stream link.")
