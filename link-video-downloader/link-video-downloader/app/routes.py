@main_bp.route('/api/info', methods=['POST'])
def get_info():
    """Fetches video metadata and direct streaming links safely."""
    try:
        data = request.get_json(silent=True) or {}
        url = data.get('url') or request.form.get('url')
        
        if not url:
            return jsonify({"error": "Please provide a valid media URL."}), 400

        service = _get_service()
        info_object = service.fetch_info(url)
        
        # FIX: Convert the VideoInfo object to a dictionary before parsing
        info = info_object.to_dict() if hasattr(info_object, 'to_dict') else info_object
        
        return jsonify({
            "status": "success",
            "title": info.get('title', 'Video Download'),
            "duration": info.get('duration'),
            "thumbnail": info.get('thumbnail'),
            "extractor": info.get('extractor_key', 'extractor'),
            "url": info.get('url') or info.get('webpage_url'),
            "qualities": info.get('qualities', [])
        }), 200

    except Exception as e:
        error_message = str(e)
        current_app.logger.error(f"[API Info Error]: {error_message}")
        
        if "bot" in error_message.lower() or "restricted" in error_message.lower() or "login" in error_message.lower():
            clean_error = "Platform security blocked cloud server access. Please try updating your cookies or use a residential IP."
        else:
            clean_error = error_message
            
        return jsonify({"status": "error", "error": clean_error}), 400
