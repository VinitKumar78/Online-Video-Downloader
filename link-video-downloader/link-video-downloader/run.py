import os

# ==========================================
# 1. CLOUD COOKIE GENERATOR (RENDER SECURITY)
# ==========================================
# Grabs the cookies text from Render Environment Variables and writes it to cookies.txt
cookies_content = os.getenv("COOKIES_CONTENT")

if cookies_content:
    # Handle newlines properly when injected via cloud environment variables
    formatted_content = cookies_content.replace("\\n", "\n")
    with open("cookies.txt", "w", encoding="utf-8") as f:
        f.write(formatted_content)
    print("🔒 Successfully generated cookies.txt from Render Environment Variables.")
else:
    print("⚠️ No COOKIES_CONTENT found. Proceeding without cloud cookies.")

# ==========================================
# 2. APPLICATION STARTUP
# ==========================================
try:
    # Supports application factory pattern (create_app)
    from app import create_app
    app = create_app()
except ImportError:
    # Fallback if your app uses direct initialization (app = Flask(__name__))
    from app import app

if __name__ == "__main__":
    # Render assigns a dynamic PORT environment variable; fallback to 5000 for local testing
    port = int(os.environ.get("PORT", 5000))
    
    # Run server bound to 0.0.0.0 so external cloud traffic can reach it
    app.run(host="0.0.0.0", port=port, debug=False)
