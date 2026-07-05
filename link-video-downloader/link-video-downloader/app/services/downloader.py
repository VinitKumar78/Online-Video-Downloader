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

        ydl_opts = {
            "quiet": True, 
            "no_warnings": True, 
            "skip_download": True,
            "ffmpeg_location": ffmpeg_path  # Bundled configuration path for free data centers
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
            
        except yt_dlp.utils.DownloadError as exc:
            if "Unsupported URL" in str(exc):
                logger.info("Unsupported URL detected by yt-dlp. Attempting HTTP Fallback for: %s", url)
                try:
                    target_url = self._resolve_direct_url(url)
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Referer": "https://www.diskwala.com/"
                    }
                    response = requests.head(target_url, headers=headers, allow_redirects=True, timeout=5)
                    if response.status_code >= 400:
                        response = requests.get(target_url, headers=headers, stream=True, timeout=5)
                    
                    if response.status_code == 200:
                        parsed_url = urlparse(url)
                        base_name = os.path.basename(parsed_url.path) or "cloud_file"
                        if "-" in base_name or len(base_name) > 20:
                            base_name = "Cloud Video"
                        
                        return VideoInfo(
                            title=base_name,
                            thumbnail=None,
                            duration=None,
                            uploader="Direct File Link",
                            qualities=[{"height": 0, "label": "Source File"}]
                        )
                except Exception as req_err:
                    raise ExtractionError(f"Direct connection to file server failed: {str(req_err)}") from req_err
                    
            logger.warning("yt-dlp failed to extract info for %s: %s", url, exc)
            raise ExtractionError(str(exc)) from exc
        except Exception as exc:
            logger.exception("Unexpected error extracting info for %s", url)
            raise ExtractionError(str(exc)) from exc

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
        is_direct_http = (int(height) == 0)
        
        if is_direct_http:
            ydl_opts = {
                "quiet": True, 
                "simulate": True,
                "ffmpeg_location": ffmpeg_path
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=False)
                    is_direct_http = False
            except Exception:
                is_direct_http = True

        # -- Path A: Fallback Direct HTTP Stream Download Handler --
        if is_direct_http:
            try:
                target_url = self._resolve_direct_url(url)
                logger.info("Executing background HTTP request stream for Job %s to: %s", job_id, target_url)
                
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.diskwala.com/",
                    "Origin": "https://www.diskwala.com"
                }
                
                # Execute session handshake to follow redirects safely
                session = requests.Session()
                response = session.get(target_url, headers=headers, stream=True, timeout=60)
                response.raise_for_status()
                
                # SENSOR SECURITY GUARD: Ensure we didn't receive an HTML firewall landing page block
                content_type = response.headers.get('Content-Type', '')
                if "text/html" in content_type:
                    raise ExtractionError("Diskwala server denied direct streaming access. Anti-bot restriction triggered.")

                total_size = int(response.headers.get('content-length', 0))
                content_disp = response.headers.get('Content-Disposition', '')
                inferred_filename = "video.mp4"
                
                if "filename=" in content_disp:
                    try:
                        inferred_filename = content_disp.split("filename=")[-1].strip('"\'')
                    except Exception:
                        pass
                
                _, ext = os.path.splitext(inferred_filename)
                if not ext:
                    ext = f".{self.output_format}"
                    
                target_filename = f"{job_id}{ext}"
                target_path = os.path.join(self.download_dir, target_filename)
                
                downloaded = 0
                with open(target_path, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=131072):
                        if chunk:
                            file.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = int((downloaded / total_size) * 100)
                                job_store.update(job_id, progress=f"{percent}%")
                            else:
                                job_store.update(job_id, progress="Streaming...")
                                
                job_store.update(
                    job_id,
                    status=JobStatus.DONE,
                    filename=target_filename,
                    title=sanitize_filename(inferred_filename.split('.')[0], self.max_filename_length)
                )
                logger.info("Direct HTTP stream Job %s completed safely: %s", job_id, target_filename)
                return
            except Exception as exc:
                logger.exception("Direct HTTP fallback streaming loop failed for Job %s", job_id)
                job_store.update(job_id, status=JobStatus.ERROR, error=str(exc)[:300])
                return

        # -- Path B: Standard Native yt-dlp Video Extraction Pipeline --
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
            "ffmpeg_location": ffmpeg_path,  # Dynamically points yt-dlp to the imageio binary on Render
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
            logger.info("Job %s completed: %s", job_id, filename)
        except Exception as exc:
            logger.exception("Job %s failed", job_id)
            job_store.update(job_id, status=JobStatus.ERROR, error=str(exc)[:300])