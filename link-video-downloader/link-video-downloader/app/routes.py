import logging
import requests
from flask import Blueprint, jsonify, request, redirect, render_template, Response, stream_with_context

from app.services.downloader import DownloaderService
from app.services.exceptions import DownloaderException, ExtractionError, InvalidURLError

logger = logging.getLogger(__name__)

# Initialize your blueprint as defined in your setup
main_bp = Blueprint("main", __name__)

# Boot up the downloader service
downloader = DownloaderService(download_dir="downloads")


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/api/info", methods=["POST"])
def fetch_info():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "URL parameter is required."}), 400

    try:
        info = downloader.fetch_info(url)
        return jsonify(info.to_dict()), 200
    except (DownloaderException, ExtractionError, InvalidURLError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Unexpected error in /api/info")
        return jsonify({"error": "An internal error occurred while fetching video info."}), 500


@main_bp.route("/api/stream-download", methods=["GET"])
def stream_download():
    """Instantly routes the media file into the user's native browser download tray."""
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL parameter is required."}), 400

    try:
        direct_url, filename = downloader.get_direct_stream(url)
        
        # SMART ROUTING: If the backend used the Cloud Bypass Pool, it issues an instant redirect.
        # This triggers the browser's native download UI immediately without opening a new tab!
        if any(bypass_node in direct_url for bypass_node in ["cobalt", "wuk"]):
            return redirect(direct_url)
        
        # If the backend successfully resolved a native yt-dlp link, pipe the chunked stream
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*"
        }
        
        external_req = requests.get(direct_url, headers=headers, stream=True, timeout=15)
        external_req.raise_for_status()
        
        def generate():
            for chunk in external_req.iter_content(chunk_size=131072):
                if chunk:
                    yield chunk

        resp = Response(stream_with_context(generate()), content_type="video/mp4")
        resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        
        total_length = external_req.headers.get("Content-Length")
        if total_length:
            resp.headers["Content-Length"] = total_length
            
        return resp

    except (DownloaderException, ExtractionError, InvalidURLError) as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Unexpected error in /api/stream-download")
        return jsonify({"error": "Failed to initiate live media stream."}), 500
