import logging
import os
from flask import Blueprint, current_app, jsonify, render_template, request, send_from_directory

from app.services.downloader import DownloaderService
from app.services.exceptions import ExtractionError, InvalidURLError
from app.services.job_store import JobStatus, job_store

logger = logging.getLogger(__name__)

# This is the line that was missing!
main_bp = Blueprint("main", __name__)

def _get_service() -> DownloaderService:
    """Helper to safely initialize the downloader service with Flask config parameters."""
    return DownloaderService(
        download_dir=current_app.config.get("DOWNLOAD_DIR", "downloads"),
        output_format=current_app.config.get("OUTPUT_FORMAT", "mp4"),
        max_filename_length=current_app.config.get("MAX_FILENAME_LENGTH", 200),
    )

@main_bp.route("/")
def index():
    """Renders the main frontend application UI."""
    return render_template("index.html")

@main_bp.route("/api/health")
def health():
    """Simple health check endpoint."""
    return jsonify({"status": "ok"})

@main_bp.route("/api/info", methods=["POST"])
def get_info():
    """Fetches video metadata and direct streaming links safely."""
    try:
        payload = request.get_json(silent=True) or {}
        url = (payload.get("url") or request.form.get("url") or "").strip()

        if not url:
            return jsonify({"error": "Please provide a valid media URL."}), 400

        service = _get_service()
        info_object = service.fetch_info(url)
        
        # Converts the VideoInfo object to a dictionary before parsing
        info = info_object.to_dict() if hasattr(info_object, 'to_dict') else info_object

        return jsonify({
            "status": "success",
            "title": info.get('title', 'Video Download'),
            "duration": info.get('duration'),
            "thumbnail": info.get('thumbnail'),
            "extractor": info.get('uploader', 'extractor'),
            "url": url,
            "qualities": info.get('qualities', [])
        }), 200

    except InvalidURLError as exc:
        return jsonify({"status": "error", "error": str(exc)}), 400
    except ExtractionError as exc:
        return jsonify({"status": "error", "error": f"Could not process this link: {str(exc)[:200]}"}), 422
    except Exception as e:
        error_message = str(e)
        current_app.logger.error(f"[API Info Error]: {error_message}")
        
        # Catch bot blocks and send clean UI messages instead of server crashes
        if "bot" in error_message.lower() or "restricted" in error_message.lower() or "login" in error_message.lower():
            clean_error = "Platform security blocked cloud server access. Please try updating your cookies or use a residential IP."
        else:
            clean_error = error_message
            
        return jsonify({"status": "error", "error": clean_error}), 400


@main_bp.route("/api/download", methods=["POST"])
def start_download():
    """Initiates an asynchronous background download job."""
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or request.form.get("url") or "").strip()
    height = payload.get("height", 0)

    if not url:
        return jsonify({"error": "Please provide a valid media URL."}), 400

    try:
        job = _get_service().start_download(url, height)
    except InvalidURLError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as e:
        logger.exception("[API Download Error]")
        return jsonify({"error": f"Failed to initialize download: {str(e)}"}), 500

    return jsonify({"job_id": job.id})


@main_bp.route("/api/status/<job_id>")
def job_status(job_id):
    """Checks the progress of a background download job."""
    job = job_store.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job.to_dict())


@main_bp.route("/api/file/<job_id>")
def get_file(job_id):
    """Serves the completed video file to the user."""
    job = job_store.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    if job.status != JobStatus.DONE:
        return jsonify({"error": "File is not ready yet"}), 409

    extension = job.filename.rsplit(".", 1)[-1] if "." in job.filename else "mp4"
    download_name = f"{job.title or 'video'}.{extension}"

    return send_from_directory(
        current_app.config["DOWNLOAD_DIR"],
        job.filename,
        as_attachment=True,
        download_name=download_name,
    )


@main_bp.errorhandler(404)
def not_found(_error):
    return jsonify({"error": "Resource not found"}), 404


@main_bp.errorhandler(500)
def server_error(error):
    logger.exception("Unhandled server error")
    return jsonify({"error": "An unexpected server error occurred"}), 500
