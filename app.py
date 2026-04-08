"""
HenAi Proxy Server - Routes traffic to Hugging Face Space with Keep-Alive
Your actual app runs on HF Spaces, this provides a clean URL and prevents spin-down
"""

from flask import Flask, request, Response, jsonify
from flask_cors import CORS
import requests
import os
import threading
import time
import logging
from datetime import datetime
import atexit

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# ============= CONFIGURATION =============
# Your Hugging Face Space URL - set this in Render environment variables
HF_SPACE_URL = os.environ.get('HF_SPACE_URL', 'https://YOUR_USERNAME-YOUR_SPACE.hf.space')
KEEP_ALIVE_INTERVAL = int(os.environ.get('KEEP_ALIVE_INTERVAL', 300))  # 5 minutes default
PORT = int(os.environ.get('PORT', 5000))

# Remove trailing slash if present
HF_SPACE_URL = HF_SPACE_URL.rstrip('/')

logger.info(f"🚀 HenAi Proxy Starting...")
logger.info(f"📍 Target HF Space: {HF_SPACE_URL}")
logger.info(f"⏱️  Keep-alive interval: {KEEP_ALIVE_INTERVAL} seconds")
logger.info(f"🔌 Port: {PORT}")

# ============= KEEP-ALIVE MECHANISM =============

class KeepAliveManager:
    """Manages periodic pings to keep HF Space alive"""
    
    def __init__(self, url, interval=300):
        self.url = url
        self.interval = interval
        self.running = False
        self.thread = None
        self.ping_count = 0
        self.success_count = 0
        self.fail_count = 0
        
    def start(self):
        """Start the keep-alive thread"""
        if self.running:
            logger.warning("Keep-alive already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info(f"✅ Keep-alive started (every {self.interval} seconds)")
    
    def stop(self):
        """Stop the keep-alive thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("🛑 Keep-alive stopped")
    
    def _run(self):
        """Background thread that pings the HF Space"""
        while self.running:
            try:
                self.ping_count += 1
                start_time = time.time()
                
                # Ping the main page
                response = requests.get(
                    self.url,
                    timeout=30,
                    headers={'User-Agent': 'Render-Proxy-KeepAlive/1.0'}
                )
                
                elapsed = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    self.success_count += 1
                    logger.info(f"💓 Keep-alive #{self.ping_count}: OK ({elapsed:.0f}ms)")
                else:
                    self.fail_count += 1
                    logger.warning(f"⚠️ Keep-alive #{self.ping_count}: HTTP {response.status_code} ({elapsed:.0f}ms)")
                
                # Also try to ping the health endpoint if it exists
                try:
                    health_response = requests.get(
                        f"{self.url}/health",
                        timeout=10,
                        headers={'User-Agent': 'Render-Proxy-KeepAlive/1.0'}
                    )
                    if health_response.status_code == 200:
                        logger.debug(f"🏥 Health check passed")
                except:
                    pass  # Health endpoint might not exist
                    
            except requests.exceptions.Timeout:
                self.fail_count += 1
                logger.error(f"❌ Keep-alive #{self.ping_count}: Timeout")
            except requests.exceptions.ConnectionError:
                self.fail_count += 1
                logger.error(f"❌ Keep-alive #{self.ping_count}: Connection error")
            except Exception as e:
                self.fail_count += 1
                logger.error(f"❌ Keep-alive #{self.ping_count}: {str(e)}")
            
            # Wait for next ping
            time.sleep(self.interval)
    
    def get_stats(self):
        """Get keep-alive statistics"""
        return {
            'ping_count': self.ping_count,
            'success_count': self.success_count,
            'fail_count': self.fail_count,
            'success_rate': round((self.success_count / self.ping_count * 100) if self.ping_count > 0 else 0, 2),
            'running': self.running,
            'target_url': self.url,
            'interval': self.interval
        }

# Initialize keep-alive manager
keep_alive = KeepAliveManager(HF_SPACE_URL, KEEP_ALIVE_INTERVAL)

# ============= PROXY REQUEST HANDLER =============

def should_skip_proxy(path):
    """Check if this path should be handled locally instead of proxied"""
    skip_paths = ['/health', '/stats', '/keep-alive-status', '/proxy-info']
    return path in skip_paths

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
def proxy(path):
    """Forward all requests to Hugging Face Space"""
    
    # Handle local routes first
    if should_skip_proxy(path):
        return handle_local_route(path)
    
    # Build the target URL
    target_url = f"{HF_SPACE_URL}/{path}" if path else HF_SPACE_URL
    
    # Get request data
    data = request.get_data()
    headers = {}
    
    # Forward relevant headers (skip host and content-length)
    for key, value in request.headers.items():
        key_lower = key.lower()
        if key_lower not in ['host', 'content-length', 'content-encoding', 'transfer-encoding']:
            headers[key] = value
    
    # Add X-Forwarded headers
    headers['X-Forwarded-For'] = request.remote_addr
    headers['X-Forwarded-Proto'] = request.scheme
    headers['X-Forwarded-Host'] = request.host
    
    # Log the request (only log non-static files to reduce noise)
    is_static = any(ext in path for ext in ['.css', '.js', '.png', '.jpg', '.ico', '.svg'])
    if not is_static:
        logger.info(f"🔄 Proxying {request.method} {path} -> {target_url}")
    
    try:
        # Forward the request
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=data,
            cookies=request.cookies,
            allow_redirects=False,
            timeout=60
        )
        
        # Prepare response headers
        response_headers = {}
        for key, value in resp.headers.items():
            key_lower = key.lower()
            if key_lower not in ['content-encoding', 'content-length', 'transfer-encoding', 'connection']:
                response_headers[key] = value
        
        # Add caching headers for static assets
        if any(ext in path for ext in ['.css', '.js', '.png', '.jpg', '.ico', '.svg']):
            response_headers['Cache-Control'] = 'public, max-age=86400'  # Cache for 1 day
        
        return Response(
            response=resp.content,
            status=resp.status_code,
            headers=response_headers
        )
        
    except requests.exceptions.Timeout:
        logger.error(f"⏰ Timeout proxying {path}")
        return jsonify({
            'error': 'Request timeout',
            'message': 'The Hugging Face Space took too long to respond. It might be starting up.'
        }), 504
        
    except requests.exceptions.ConnectionError:
        logger.error(f"🔌 Connection error proxying {path}")
        return jsonify({
            'error': 'Connection error',
            'message': f'Could not connect to {HF_SPACE_URL}. The Space might be down.'
        }), 502
        
    except Exception as e:
        logger.error(f"💥 Unexpected error proxying {path}: {str(e)}")
        return jsonify({
            'error': 'Proxy error',
            'message': str(e)
        }), 500

# ============= LOCAL ROUTES (not proxied) =============

def handle_local_route(path):
    """Handle routes that don't get proxied to HF"""
    
    if path == 'health':
        # Health check endpoint for Render
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'proxy_target': HF_SPACE_URL,
            'keep_alive': keep_alive.get_stats()
        })
    
    elif path == 'stats':
        # Detailed statistics
        return jsonify({
            'proxy': {
                'target_url': HF_SPACE_URL,
                'status': 'running'
            },
            'keep_alive': keep_alive.get_stats(),
            'server': {
                'start_time': start_time.isoformat() if 'start_time' in dir() else None,
                'uptime_seconds': (datetime.now() - start_time).total_seconds() if 'start_time' in dir() else 0
            }
        })
    
    elif path == 'keep-alive-status':
        # Simple keep-alive status
        stats = keep_alive.get_stats()
        return jsonify({
            'running': stats['running'],
            'success_rate': f"{stats['success_rate']}%",
            'pings': stats['ping_count'],
            'last_check': datetime.now().isoformat()
        })
    
    elif path == 'proxy-info':
        # Information about the proxy
        return jsonify({
            'name': 'HenAi Proxy Server',
            'version': '1.0.0',
            'target_space': HF_SPACE_URL,
            'keep_alive_interval': KEEP_ALIVE_INTERVAL,
            'documentation': 'https://github.com/yourusername/henai-proxy'
        })
    
    else:
        return jsonify({'error': 'Not found'}), 404

# ============= SIMPLE FRONTEND (optional - shows proxy is working) =============

@app.route('/_proxy_status')
def proxy_status():
    """Simple HTML page showing proxy status"""
    stats = keep_alive.get_stats()
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>HenAi Proxy Status</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 50px; background: #0d0d0d; color: #f5f5f5; }}
            .container {{ max-width: 800px; margin: auto; background: #1a1a1a; padding: 30px; border-radius: 16px; }}
            h1 {{ color: #6366f1; }}
            .status {{ padding: 20px; background: #0d0d0d; border-radius: 8px; margin: 20px 0; }}
            .good {{ color: #22c55e; }}
            .bad {{ color: #ef4444; }}
            .info {{ color: #a3a3a3; }}
            a {{ color: #6366f1; }}
        </style>
        <meta http-equiv="refresh" content="30">
    </head>
    <body>
        <div class="container">
            <h1>🔄 HenAi Proxy Server</h1>
            <p>This proxy forwards requests to your Hugging Face Space.</p>
            
            <div class="status">
                <h3>📡 Proxy Status</h3>
                <p>Target: <code>{HF_SPACE_URL}</code></p>
                <p>Status: <span class="good">✓ Running</span></p>
            </div>
            
            <div class="status">
                <h3>💓 Keep-Alive Status</h3>
                <p>Running: <span class="good">✓ Yes</span></p>
                <p>Total Pings: {stats['ping_count']}</p>
                <p>Successful: {stats['success_count']}</p>
                <p>Failed: {stats['fail_count']}</p>
                <p>Success Rate: <span class="{'good' if stats['success_rate'] > 80 else 'bad'}">{stats['success_rate']}%</span></p>
                <p>Interval: {stats['interval']} seconds</p>
            </div>
            
            <div class="status">
                <h3>🔗 Access Your App</h3>
                <p>Your app is available at: <a href="/">this same URL</a></p>
                <p>Direct HF Space: <a href="{HF_SPACE_URL}" target="_blank">{HF_SPACE_URL}</a></p>
            </div>
            
            <div class="info">
                <small>Page auto-refreshes every 30 seconds | Proxy v1.0</small>
            </div>
        </div>
    </body>
    </html>
    """

# ============= STARTUP =============

start_time = datetime.now()

@app.before_first_request
def startup():
    """Initialize on first request"""
    logger.info("🚀 Proxy server ready for first request")

# Start keep-alive when app starts
keep_alive.start()

# Clean shutdown
def shutdown():
    logger.info("🛑 Shutting down proxy server...")
    keep_alive.stop()

atexit.register(shutdown)

if __name__ == '__main__':
    logger.info(f"🎯 Starting HenAi Proxy on port {PORT}")
    logger.info(f"📍 Proxying to: {HF_SPACE_URL}")
    logger.info(f"💓 Keep-alive active every {KEEP_ALIVE_INTERVAL} seconds")
    logger.info(f"🔗 Visit http://localhost:{PORT} to see your app")
    app.run(host='0.0.0.0', port=PORT, debug=False)
