"""
HenAi Admin Proxy
Serves admin panel from HF Space with authentication
Only accessible to users with admin credentials
"""

from flask import Flask, request, Response, render_template_string, session, redirect, url_for, flash
import requests
import os
import logging
from functools import wraps
from datetime import timedelta, datetime

# ===========================================
# LOGGING CONFIGURATION
# ===========================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===========================================
# FLASK APP INITIALIZATION
# ===========================================

app = Flask(__name__)

# ===========================================
# LOAD CONFIGURATION FROM ENVIRONMENT VARIABLES
# ===========================================

# These MUST be set in Render Environment Variables
SECRET_KEY = os.environ.get('FLASK_SECRET_KEY')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
HF_SPACE_URL = os.environ.get('HF_SPACE_URL')

# Validate required environment variables
if not SECRET_KEY:
    raise ValueError("FLASK_SECRET_KEY environment variable is required!")
if not ADMIN_USERNAME:
    raise ValueError("ADMIN_USERNAME environment variable is required!")
if not ADMIN_PASSWORD:
    raise ValueError("ADMIN_PASSWORD environment variable is required!")
if not HF_SPACE_URL:
    raise ValueError("HF_SPACE_URL environment variable is required!")

# Admin routes prefix on HF Space
ADMIN_ROUTE_PREFIX = '/admin'

# Apply configuration
app.config['SECRET_KEY'] = SECRET_KEY

# Session configuration - 8 hour timeout for admin
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True if using HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Log configuration status (without exposing secrets)
logger.info("=" * 50)
logger.info("Admin Proxy Configuration:")
logger.info(f"  HF_SPACE_URL: {HF_SPACE_URL}")
logger.info(f"  ADMIN_USERNAME: {'✅ Set' if ADMIN_USERNAME else '❌ Missing'}")
logger.info(f"  SECRET_KEY: {'✅ Set' if SECRET_KEY else '❌ Missing'}")
logger.info(f"  ADMIN_PASSWORD: {'✅ Set' if ADMIN_PASSWORD else '❌ Missing'}")
logger.info("=" * 50)

# ===========================================
# HELPER FUNCTIONS
# ===========================================

def admin_required(f):
    """Decorator to require admin login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Please login as admin to access this page.', 'warning')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function


def verify_admin_credentials(username, password):
    """Verify admin credentials against environment variables"""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

# ===========================================
# ADMIN LOGIN PAGE (HTML TEMPLATE)
# ===========================================

ADMIN_LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HenAi Admin Login</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0f12 0%, #09090b 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        
        .login-container {
            max-width: 420px;
            width: 100%;
        }
        
        .login-card {
            background: #141418;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 24px;
            padding: 40px 32px;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
        }
        
        .logo {
            text-align: center;
            margin-bottom: 32px;
        }
        
        .logo-icon {
            width: 56px;
            height: 56px;
            background: linear-gradient(135deg, #7c6aff, #a855f7);
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 16px;
            font-size: 24px;
            font-weight: 800;
            color: white;
            font-family: 'Syne', monospace;
        }
        
        .logo h1 {
            font-size: 24px;
            font-weight: 700;
            color: #eeeef5;
            letter-spacing: -0.02em;
        }
        
        .logo p {
            font-size: 13px;
            color: #6b6b80;
            margin-top: 6px;
        }
        
        .admin-badge {
            display: inline-block;
            background: rgba(124,106,255,0.15);
            border: 1px solid rgba(124,106,255,0.25);
            border-radius: 30px;
            padding: 4px 12px;
            font-size: 11px;
            font-weight: 600;
            color: #9b8dff;
            margin-bottom: 16px;
            letter-spacing: 0.5px;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-label {
            display: block;
            font-size: 13px;
            font-weight: 500;
            color: #9191a8;
            margin-bottom: 8px;
        }
        
        .form-input {
            width: 100%;
            padding: 12px 16px;
            background: #1a1a20;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            color: #d4d4e0;
            font-size: 14px;
            font-family: inherit;
            transition: all 0.2s ease;
        }
        
        .form-input:focus {
            outline: none;
            border-color: #7c6aff;
            box-shadow: 0 0 0 3px rgba(124,106,255,0.15);
        }
        
        .form-input::placeholder {
            color: #3a3a4a;
        }
        
        .btn-login {
            width: 100%;
            padding: 12px 20px;
            background: #7c6aff;
            border: none;
            border-radius: 12px;
            color: white;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            margin-top: 8px;
        }
        
        .btn-login:hover {
            background: #9b8dff;
            transform: translateY(-1px);
        }
        
        .btn-login:active {
            transform: translateY(0);
        }
        
        .alert {
            padding: 12px 16px;
            border-radius: 12px;
            margin-bottom: 20px;
            font-size: 13px;
        }
        
        .alert-danger {
            background: rgba(248,113,113,0.1);
            border: 1px solid rgba(248,113,113,0.2);
            color: #f87171;
        }
        
        .alert-success {
            background: rgba(52,211,153,0.1);
            border: 1px solid rgba(52,211,153,0.2);
            color: #34d399;
        }
        
        .alert-info {
            background: rgba(96,165,250,0.1);
            border: 1px solid rgba(96,165,250,0.2);
            color: #60a5fa;
        }
        
        .footer-note {
            text-align: center;
            margin-top: 24px;
            font-size: 12px;
            color: #3a3a4a;
        }
        
        .footer-note a {
            color: #7c6aff;
            text-decoration: none;
        }
        
        .footer-note a:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-card">
            <div class="logo">
                <div class="logo-icon">
                    <svg width="28" height="28" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
                        <rect x="33" y="20" width="9" height="60" rx="4.5" fill="#7c6aff"/>
                        <rect x="58" y="20" width="9" height="60" rx="4.5" fill="#7c6aff"/>
                        <path d="M42 43 C 48 43, 43 57, 58 57" stroke="#9b8dff" stroke-width="9" fill="none" stroke-linecap="round"/>
                    </svg>
                </div>
                <span class="admin-badge">ADMIN PORTAL</span>
                <h1>HenAi Admin</h1>
                <p>Secure access to administration panel</p>
            </div>
            
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="alert alert-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            
            <form method="POST" action="{{ url_for('admin_login') }}">
                <div class="form-group">
                    <label class="form-label">Username</label>
                    <input type="text" name="username" class="form-input" placeholder="Enter admin username" required autofocus>
                </div>
                <div class="form-group">
                    <label class="form-label">Password</label>
                    <input type="password" name="password" class="form-input" placeholder="Enter admin password" required>
                </div>
                <button type="submit" class="btn-login">Access Admin Panel</button>
            </form>
            <div class="footer-note">
                <a href="{{ main_site_url }}" target="_blank">← Back to Main Site</a>
            </div>
        </div>
    </div>
</body>
</html>
'''

# ===========================================
# ADMIN LOGIN ROUTE
# ===========================================

@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page - separate from main app"""
    
    # If already logged in, redirect to admin panel
    if session.get('is_admin'):
        return redirect(url_for('admin_proxy', path=''))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if verify_admin_credentials(username, password):
            session.permanent = True
            session['is_admin'] = True
            session['admin_username'] = username
            session['admin_logged_at'] = datetime.now().isoformat()
            logger.info(f"Admin login successful: {username}")
            flash('Logged in successfully.', 'success')
            return redirect(url_for('admin_proxy', path=''))
        else:
            logger.warning(f"Failed admin login attempt for: {username}")
            flash('Invalid username or password.', 'danger')
    
    # Pass the main site URL to the template for the back link
    main_site_url = HF_SPACE_URL.replace('/admin', '')
    return render_template_string(ADMIN_LOGIN_TEMPLATE, main_site_url=main_site_url)


@app.route('/admin-logout')
def admin_logout():
    """Admin logout"""
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('admin_login'))


# ===========================================
# PROXY ROUTE - Forwards to HF Space /admin/*
# ===========================================

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
@admin_required
def admin_proxy(path):
    """
    Forward ALL admin requests to HF Space /admin endpoint
    Only accessible after admin login
    """
    
    # Build target URL - always under /admin on HF Space
    if path:
        target_url = f"{HF_SPACE_URL}{ADMIN_ROUTE_PREFIX}/{path}"
    else:
        target_url = f"{HF_SPACE_URL}{ADMIN_ROUTE_PREFIX}"
    
    # Prepare headers (remove problematic ones)
    headers = {}
    for key, value in request.headers.items():
        key_lower = key.lower()
        if key_lower not in ['host', 'content-length', 'content-encoding']:
            headers[key] = value
    
    # Add admin authentication header for HF Space to verify
    headers['X-Admin-Authenticated'] = 'true'
    headers['X-Admin-Username'] = session.get('admin_username', '')
    
    logger.info(f"Admin proxy: {request.method} {request.path} → {target_url}")
    
    try:
        # Forward the request to HF Space
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
        
    except requests.exceptions.Timeout:
        logger.error(f"Admin proxy timeout: {target_url}")
        return "Admin proxy timeout. Please try again.", 504
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Admin proxy connection error: {e}")
        return f"Error connecting to HenAi admin panel. Please check if the server is running. ({str(e)})", 503
    except Exception as e:
        logger.error(f"Admin proxy error: {e}")
        return f"Admin proxy error: {str(e)}", 500


# ===========================================
# HEALTH CHECK ENDPOINT
# ===========================================

@app.route('/health')
def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "HenAi Admin Proxy",
        "proxy_to": f"{HF_SPACE_URL}{ADMIN_ROUTE_PREFIX}",
        "admin_authenticated": session.get('is_admin', False)
    }


# ===========================================
# RUN
# ===========================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Admin Proxy running on port {port}")
    logger.info(f"📍 Forwarding to: {HF_SPACE_URL}{ADMIN_ROUTE_PREFIX}")
    app.run(host='0.0.0.0', port=port, debug=False)
