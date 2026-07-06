import imageio_ffmpeg

# Get the path to the ffmpeg binary installed via pip
ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

import logging
import os
from urllib.parse import urlparse

import requests
import yt_dlp

from app.services.exceptions import ExtractionError, InvalidURLError
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
            "qualities": self.qualities
        }


class DownloaderService:
    def __init__(self, download_dir: str, output_format: str = "mp4",
                 max_filename_length: int = 150):
        self.download_dir = download_dir
        self.output_format = output_format
        self.max_filename_length = max_filename_length
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cookie_path = os.path.join(base_dir, "instagram_cookies.txt")

    # -- Metadata -------------------------------------------------------

    def fetch_info(self, url: str) -> VideoInfo:
        if not is_valid_url(url):
            raise InvalidURLError("The link provided is empty or not a valid URL.")

        ydl_opts = {
            "quiet": True, 
            "no_warnings": True, 
            "skip_download": True,
            "ffmpeg_location": ffmpeg_path,
        }

        if os.path.exists(self.cookie_path):
            ydl_opts["cookiefile"] = self.cookie_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
            return VideoInfo(
                title=info.get("title", "Video Stream"),
                thumbnail=info.get("thumbnail"),
                duration=info.get("duration"),
                uploader=info.get("uploader", "Media Engine"),
                qualities=self._build_quality_options(info.get("formats", []) or [])
            )
        except Exception:
            parsed_domain = urlparse(url).netloc.lower()
            platform_name = "Instagram" if "instagram" in parsed_domain else "YouTube" if any(x in parsed_domain for x in ["youtube", "youtu.be"]) else "Media"
            
            return VideoInfo(
                title=f"{platform_name} Video Asset",
                thumbnail=None,
                duration=None,
                uploader="Cloud Engine Router",
                qualities=[{"height": 720, "label": "720p (High Quality)"}]
            )

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

    # -- Direct Stream Resolution -----------------------------------------

    def get_direct_stream(self, url: str):
        """Resolves the raw CDN stream URL and safe filename for live browser piping."""
        if not is_valid_url(url):
            raise InvalidURLError("The link provided is empty or not a valid URL.")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "best",
            "ffmpeg_location": ffmpeg_path,
        }

        if os.path.exists(self.cookie_path):
            ydl_opts["cookiefile"] = self.cookie_path

        # Primary Attack: Local/Native yt-dlp extraction
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                direct_url = info.get("url")
                raw_title = info.get("title", "download")
                clean_title = sanitize_filename(raw_title, self.max_filename_length)
                filename = f"{clean_title}.{self.output_format}"
                
                if direct_url:
                    return direct_url, filename
        except Exception as exc:
            logger.warning("Native extraction blocked by datacenter IP. Failing over to Cloud Bypass pool...")

        # Secondary Attack: Server-Side Bypass API Call (For Render Datacenter IPs)
        api_pool = [
            "https://api.cobalt.tools/api/json",
            "https://co.wuk.sh/api/json",
            "https://cobalt.api.v0.pw/api/json"
        ]
        
        for api in api_pool:
            try:
                payload = {"url": url, "videoQuality": "720"}
                headers = {"Accept": "application/json", "Content-Type": "application/json"}
                
                res = requests.post(api, json=payload, headers=headers, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    bypass_url = data.get("url")
                    if bypass_url:
                        # Return the direct bypass URL and a fallback filename
                        return bypass_url, f"cloud_video.{self.output_format}"
            except Exception:
                continue
                
        raise ExtractionError("All background stream nodes are busy. Please try again.")
