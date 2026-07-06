import os
from flask import Blueprint, request, jsonify, send_file, current_app
from app.services.downloader import DownloaderService

main_bp = Blueprint('main', __name__)

def _get_service():
    """Helper to safely initialize the downloader service with Flask config parameters."""
    return DownloaderService(
        download_dir=current_app.config.get("DOWNLOAD_DIR", "downloads"),
        output_format=current_app.config.get("OUTPUT_FORMAT", "%(id)s.%(ext)s"),
        max_filename_length=current_app.config.get("MAX_FILENAME_LENGTH", 200),
    )

@main_bp.route('/', methods=['GET'])
def index():
    """Renders the main frontend application UI."""
    from flask import render_template
    return render_template('index.html')

@main_bp.route('/api/info', methods=['POST'])
def get_info():
    """Fetches video metadata and direct streaming links safely."""
    try:
        data = request.get_json(silent=True) or {}
        url = data.get('url') or request.form.get('url')
        
        if not url:
            return jsonify({"error": "Please provide a valid media URL."}), 400

        service = _get_service()
        info = service.fetch_info(url)
        
        return jsonify({
            "status": "success",
            "title": info.get('title', 'Video Download'),
            "duration": info.get('duration'),
            "thumbnail": info.get('thumbnail'),
            "extractor": info.get('extractor_key'),
            "url": info.get('url') or info.get('webpage_url')
        }), 200

    except Exception as e:
        error_message = str(e)
        current_app.logger.error(f"[API Info Error]: {error_message}")
        
        # Format user-friendly error messages for common cloud restrictions
        if "bot" in error_message.lower() or "restricted" in error_message.lower() or "login" in error_message.lower():
            clean_error = "Platform security blocked cloud server access. Please try updating your cookies or use a residential IP."
        else:
            clean_error = error_message
            
        return jsonify({"status": "error", "error": clean_error}), 400

@main_bp.route('/api/stream-download', methods=['GET'])
def stream_download():
    """Streams the video file directly to the user or triggers server download."""
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({"error": "Missing URL parameter."}), 400

        service = _get_service()
        
        # Execute local download on the server
        filepath = service.download_video(url)
        
        if not filepath or not os.path.exists(filepath):
            return jsonify({"error": "File extraction failed on cloud storage."}), 500

        # Send file to browser as an attachment
        return send_file(
            filepath,
            as_attachment=True,
            download_name=os.path.basename(filepath)
        )

    except Exception as e:
        error_message = str(e)
        current_app.logger.error(f"[API Download Error]: {error_message}")
        return jsonify({"status": "error", "error": f"Download failed: {error_message}"}), 400
