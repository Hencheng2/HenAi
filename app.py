"""
HenAi Render Proxy - Simple pass-through to Hugging Face Space
Your actual frontend from HF Space will be shown, nothing else
"""

from flask import Flask, request, Response
import requests
import os
import threading
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Your Hugging Face Space API endpoint
HF_SPACE_URL = os.environ.get('HF_SPACE_URL', 'https://henley2035-henai.hf.space')
HF_SPACE_URL = HF_SPACE_URL.rstrip('/')

# Keep-alive interval (prevents spin-down)
KEEP_ALIVE_INTERVAL = int(os.environ.get('KEEP_ALIVE_INTERVAL', 240))

# ============= PROXY EVERYTHING =============

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD'])
def proxy(path):
    """Forward ALL requests to HF Space - returns YOUR app exactly as-is"""
    
    # Build target URL
    if path:
        target_url = f"{HF_SPACE_URL}/{path}"
    else:
        target_url = HF_SPACE_URL
    
    # Prepare headers (remove problematic ones)
    headers = {}
    for key, value in request.headers.items():
        key_lower = key.lower()
        if key_lower not in ['host', 'content-length', 'content-encoding']:
            headers[key] = value
    
    try:
        # Forward the request to your HF Space
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            timeout=120,
            allow_redirects=True
        )
        
        # Return the response exactly as received
        return Response(
            response=resp.content,
            status=resp.status_code,
            headers=dict(resp.headers)
        )
        
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return f"Error connecting to HenAi. Please wait a moment and try again. ({str(e)})", 503

# ============= SIMPLE KEEP-ALIVE =============

def keep_alive():
    """Background thread to keep the space warm"""
    while True:
        try:
            requests.get(HF_SPACE_URL, timeout=30)
            logger.info(f"💓 Keep-alive ping to {HF_SPACE_URL}")
        except Exception as e:
            logger.warning(f"Keep-alive ping failed: {e}")
        time.sleep(KEEP_ALIVE_INTERVAL)

# Start keep-alive thread
thread = threading.Thread(target=keep_alive, daemon=True)
thread.start()

# ============= RUN =============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Proxy running on port {port}")
    logger.info(f"📍 Forwarding to: {HF_SPACE_URL}")
    app.run(host='0.0.0.0', port=port, debug=False)
