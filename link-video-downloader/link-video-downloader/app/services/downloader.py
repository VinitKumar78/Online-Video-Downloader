import os
import yt_dlp
from typing import Dict, Any, Optional

# Automatically locate cookies.txt in the root directory
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
COOKIES_PATH = os.path.join(ROOT_DIR, 'cookies.txt')


def get_base_ydl_opts() -> Dict[str, Any]:
    """
    Returns base configuration options for yt-dlp, including anti-bot headers
    and cookie file injection if available.
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

    # Automatically attach cookies.txt if it exists in your project root
    if os.path.exists(COOKIES_PATH):
        opts['cookiefile'] = COOKIES_PATH
    else:
        print(f"[Warning] Cookies file not found at: {COOKIES_PATH}. Some platforms may block cloud requests.")

    return opts


def extract_video_info(url: str) -> Dict[str, Any]:
    """
    Extracts video metadata and direct streaming links without downloading the file locally.
    """
    opts = get_base_ydl_opts()
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Handle playlists or multi-video posts by picking the first entry
            if 'entries' in info and info['entries']:
                info = info['entries'][0]
                
            return info
    except yt_dlp.utils.DownloadError as e:
        raise Exception(f"Failed to resolve stream on cloud server: {str(e)}")
    except Exception as e:
        raise Exception(f"An unexpected error occurred while resolving video info: {str(e)}")


def download_video_file(url: str, output_dir: str = 'downloads') -> str:
    """
    Downloads the video directly to the server's local storage and returns the filepath.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    opts = get_base_ydl_opts()
    opts.update({
        'outtmpl': os.path.join(output_dir, '%(id)s_%(title).50s.%(ext)s'),
        # Fallback to single format if ffmpeg is missing on Render
        'format': 'best[ext=mp4]/bestvideo+bestaudio/best',
    })

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if 'entries' in info and info['entries']:
                info = info['entries'][0]
                
            filepath = ydl.prepare_filename(info)
            return filepath
    except yt_dlp.utils.DownloadError as e:
        raise Exception(f"Download failed: {str(e)}")
    except Exception as e:
        raise Exception(f"System error during download: {str(e)}")
