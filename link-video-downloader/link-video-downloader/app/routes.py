import logging
from flask import Blueprint, Response, current_app, jsonify, render_template, request, send_from_directory, stream_with_context
import requests

from app.services.downloader import DownloaderService
from app.services.exceptions import ExtractionError, InvalidURLError
from app.services.job_store import JobStatus, job_store

logger = logging.getLogger(__name__)

main_bp = Blueprint("main", __name__)


def _get_service() -> DownloaderService:
    return DownloaderService(
        download_dir=current_app.config["DOWNLOAD_DIR"],
        output_format=current_app.config["OUTPUT_FORMAT"],
        max_filename_length=current_app.config["MAX_FILENAME_LENGTH"],
    )


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@main_bp.route("/api/info", methods=["POST"])
def get_info():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()

    try:
        info = _get_service().fetch_info(url)
    except InvalidURLError as exc:
        return jsonify({"error": str(exc)}), 400
    except ExtractionError as exc:
        return jsonify({"error": f"Could not process this link: {str(exc)[:200]}"}), 422

    return jsonify(info.to_dict())


@main_bp.route("/api/stream-download", methods=["GET"])
def stream_download():
    """Instantly streams media directly into the browser download tray."""
    url = request.args.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL parameter is required."}), 400

    service = _get_service()
    try:
        # Extract direct stream URL and safe filename from yt-dlp engine
        direct_url, filename = service.get_direct_stream(url)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*"
        }
        
        external_req = requests.get(direct_url, headers=headers, stream=True, timeout=30)
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

    except InvalidURLError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        logger.exception("Streaming route failure: %s", exc)
        return jsonify({"error": "Failed to resolve stream on cloud server."}), 500


@main_bp.route("/api/download", methods=["POST"])
def start_download():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    height = payload.get("height", 0)

    try:
        job = _get_service().start_download(url, height)
    except InvalidURLError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"job_id": job.id})


@main_bp.route("/api/status/<job_id>")
def job_status(job_id):
    job = job_store.get(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job.to_dict())


@main_bp.route("/api/file/<job_id>")
def get_file(job_id):
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
