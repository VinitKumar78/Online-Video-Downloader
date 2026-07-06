import os
import yt_dlp
from typing import Dict, Any, Optional

# Locate root directory dynamically to find cookies.txt
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
COOKIES_PATH = os.path.join(ROOT_DIR, 'cookies.txt')


class DownloaderService:
    def __init__(
        self,
        download_dir: Optional[str] = 'downloads',
        output_dir: Optional[str] = None,
        output_format: Optional[str] = '%(id)s_%(title).50s.%(ext)s',
        max_filename_length: Optional[int] = 200,
        **kwargs
    ):
        """
        Initializes the DownloaderService and accepts Flask app configuration settings.
        Flexible keyword arguments ensure compatibility across different route setups.
        """
        # Resolve output directory using download_dir (from routes) or output_dir fallback
        dir_path = download_dir or output_dir or 'downloads'
        self.output_dir = os.path.join(ROOT_DIR, dir_path)
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

        self.output_format = output_format or '%(id)s_%(title).50s.%(ext)s'
        self.max_filename_length = max_filename_length or 200

    def get_base_opts(self) -> Dict[str, Any]:
        """
        Returns configuration options for yt-dlp including anti-bot headers
        and cookie injection for cloud hosting on Render.
        """
        opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'nocheckcertificate': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            }
        }

        # Automatically attach cookies if available on local disk or cloud environment
        if os.path.exists('cookies.txt'):
            opts['cookiefile'] = 'cookies.txt'
        elif os.path.exists(COOKIES_PATH):
            opts['cookiefile'] = COOKIES_PATH

        return opts

    def extract_info(self, url: str, download: bool = False) -> Dict[str, Any]:
        """
        Extracts video metadata and direct streaming links.
        """
        opts = self.get_base_opts()
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=download)
                # Handle playlists or multi-item posts by selecting the first entry
                if 'entries' in info and info['entries']:
                    info = info['entries'][0]
                return info
        except yt_dlp.utils.DownloadError as e:
            raise Exception(f"Failed to resolve stream on cloud server: {str(e)}")
        except Exception as e:
            raise Exception(f"An unexpected error occurred during resolution: {str(e)}")

    def get_video_info(self, url: str) -> Dict[str, Any]:
        """
        Alias for extract_info without downloading to disk.
        """
        return self.extract_info(url, download=False)

    def download_video(self, url: str) -> str:
        """
        Downloads the video directly to local server storage and returns the file path.
        """
        opts = self.get_base_opts()
        opts.update({
            'outtmpl': os.path.join(self.output_dir, '%(id)s.%(ext)s'),
            'trim_file_name': self.max_filename_length,
        })
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if 'entries' in info and info['entries']:
                    info = info['entries'][0]
                return ydl.prepare_filename(info)
        except yt_dlp.utils.DownloadError as e:
            raise Exception(f"Download failed: {str(e)}")
        except Exception as e:
            raise Exception(f"System error during download: {str(e)}")

    def download(self, url: str) -> str:
        """
        Alias for download_video.
        """
        return self.download_video(url)
