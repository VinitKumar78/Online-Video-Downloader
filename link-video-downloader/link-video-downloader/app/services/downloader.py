import os
from typing import Any, Dict, Optional
import yt_dlp

# Dynamically locate root directories to resolve cookies reliably across cloud instances
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


class DownloaderService:

    def __init__(
        self,
        download_dir: Optional[str] = 'downloads',
        output_dir: Optional[str] = None,
        output_format: Optional[str] = '%(id)s_%(title).50s.%(ext)s',
        max_filename_length: Optional[int] = 200,
        **kwargs,
    ):
        """Initializes the DownloaderService and accepts all Flask app config settings.

        **kwargs guarantees that unexpected parameters from routes.py won't
        throw TypeErrors.
        """
        dir_path = download_dir or output_dir or 'downloads'
        self.output_dir = os.path.join(ROOT_DIR, dir_path)
        if not os.path.exists(self.output_dir):
          os.makedirs(self.output_dir, exist_ok=True)

        self.output_format = output_format or '%(id)s_%(title).50s.%(ext)s'
        self.max_filename_length = max_filename_length or 200

    def get_base_opts(self) -> Dict[str, Any]:
        """Returns hardened configuration options for yt-dlp.

        Configured with mobile client emulation to bypass cloud IP bot blocks.
        """
        opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'nocheckcertificate': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'http_headers': {
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    ' (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
                ),
                'Accept': (
                    'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                ),
                'Accept-Language': 'en-US,en;q=0.9',
                'Sec-Fetch-Mode': 'navigate',
            },
            # HARDENED CLIENT CONFIGURATION: Forces yt-dlp to rely strictly on native mobile application signatures
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'android', 'mweb'],
                    'player_skip': ['webpage', 'configs'],
                }
            },
        }

        # Universal Cookie Locator: Scans all possible cloud paths for generated cookies.txt
        possible_cookie_paths = [
            os.path.abspath('cookies.txt'),
            os.path.join(ROOT_DIR, 'cookies.txt'),
            os.path.join(os.getcwd(), 'cookies.txt'),
            '/tmp/cookies.txt',
        ]

        for path in possible_cookie_paths:
          if os.path.exists(path) and os.path.getsize(path) > 0:
            opts['cookiefile'] = path
            print(
                f'🔒 [DownloaderService] Successfully attached cookies'
                f' from: {path}'
            )
            break

        return opts

    def extract_info(
        self, url: str, download: bool = False, **kwargs
    ) -> Dict[str, Any]:
        """Core metadata extraction logic.

        Safely extracts video info and handles playlists.
        """
        opts = self.get_base_opts()
        try:
          with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=download)
            if 'entries' in info and info['entries']:
              info = info['entries'][0]
            return info
        except yt_dlp.utils.DownloadError as e:
          error_msg = str(e)
          if 'Sign in to confirm' in error_msg:
            raise Exception(
                'Cloud server access restricted by platform anti-bot'
                ' protection. Please ensure valid cookies are supplied.'
            )
          raise Exception(f'Video extraction failed: {error_msg}')
        except Exception as e:
          raise Exception(f'Unexpected resolution error: {str(e)}')

    # =========================================================================
    # EXHAUSTIVE ROUTE ALIASES (Guarantees zero AttributeError crashes in routes)
    # =========================================================================

    def fetch_info(self, url: str, **kwargs) -> Dict[str, Any]:
        """Primary method called by app.routes line 38 for /api/info endpoints."""
        return self.extract_info(url, download=False, **kwargs)

    def get_info(self, url: str, **kwargs) -> Dict[str, Any]:
        """Alias for routes requesting general info resolution."""
        return self.extract_info(url, download=False, **kwargs)

    def get_video_info(self, url: str, **kwargs) -> Dict[str, Any]:
        """Alias for legacy or alternate route implementations."""
        return self.extract_info(url, download=False, **kwargs)

    def get_stream_url(self, url: str, **kwargs) -> str:
        """Resolves direct playback/stream URL for /api/stream-download endpoints."""
        info = self.extract_info(url, download=False, **kwargs)
        return info.get('url') or info.get('webpage_url') or url

    # =========================================================================
    # DOWNLOAD EXECUTION METHODS
    # =========================================================================

    def download_video(self, url: str, **kwargs) -> str:
        """Downloads the video file directly to server disk storage and returns the local path."""
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
          raise Exception(f'Download execution failed: {str(e)}')
        except Exception as e:
          raise Exception(f'System storage error during download: {str(e)}')

    def download(self, url: str, **kwargs) -> str:
        """Alias for download_video."""
        return self.download_video(url, **kwargs)
