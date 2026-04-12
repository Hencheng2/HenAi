"""
HenAi Render Proxy - Serves pages directly, only proxies API calls
"""

from flask import Flask, request, Response, jsonify, render_template_string
from flask_cors import CORS
import requests
import os
import threading
import time
import logging
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import secrets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ===========================================
# CONFIGURATION
# ===========================================

app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
CORS(app, supports_credentials=True)

HF_SPACE_URL = os.environ.get('HF_SPACE_URL', 'https://henley2035-henai.hf.space')
HF_SPACE_URL = HF_SPACE_URL.rstrip('/')

# ===========================================
# EMAIL CONFIGURATION
# ===========================================

MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)

# Temporary storage
temp_codes = {}

def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def send_email(to_email, subject, body):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        logger.warning("Email not configured")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = MAIL_DEFAULT_SENDER
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT)
        if MAIL_USE_TLS:
            server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        logger.info(f"✅ Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False

# ===========================================
# SIMPLE HTML PAGES (Served directly, no proxy)
# ===========================================

# Simple loading page while HF Space wakes up
LOADING_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>HenAi - Loading</title>
    <meta http-equiv="refresh" content="3; url=/app">
    <style>
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #09090b 0%, #0f0f12 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0;
        }
        .container {
            text-align: center;
            background: rgba(20,20,28,0.9);
            backdrop-filter: blur(20px);
            border-radius: 32px;
            padding: 40px;
            border: 1px solid rgba(255,255,255,0.08);
        }
        .spinner {
            width: 48px;
            height: 48px;
            border: 3px solid rgba(124,106,255,0.2);
            border-top-color: #7c6aff;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        h2 { color: white; margin-bottom: 8px; }
        p { color: #6b6b80; }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <div class="spinner"></div>
        <h2>Starting HenAi...</h2>
        <p>Please wait while we wake up the AI assistant.</p>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """Redirect to login or show loading page"""
    return redirect_to_hf('/login')

@app.route('/login')
def login():
    return redirect_to_hf('/login')

@app.route('/register')
def register():
    return redirect_to_hf('/register')

@app.route('/app')
def app_page():
    return redirect_to_hf('/app')

@app.route('/admin')
def admin():
    return redirect_to_hf('/admin')

@app.route('/admin-login')
def admin_login():
    return redirect_to_hf('/admin-login')

@app.route('/verify-email')
def verify_email():
    return redirect_to_hf('/verify-email')

@app.route('/reset-password')
def reset_password_page():
    return redirect_to_hf('/reset-password')

@app.route('/reset-verify')
def reset_verify():
    return redirect_to_hf('/reset-verify')

@app.route('/reset-password-new')
def reset_password_new():
    return redirect_to_hf('/reset-password-new')

def redirect_to_hf(path):
    """Redirect to HF Space with loading page if needed"""
    try:
        # Check if HF Space is responsive
        resp = requests.get(f"{HF_SPACE_URL}/api/auth/status", timeout=5)
        if resp.status_code == 200:
            # HF Space is awake, redirect
            return redirect(f"{HF_SPACE_URL}{path}")
        else:
            return LOADING_PAGE
    except:
        # HF Space is sleeping, show loading page
        return LOADING_PAGE

def redirect(location):
    """Create a redirect response"""
    from flask import redirect as flask_redirect
    return flask_redirect(location)

# ===========================================
# AUTH API ENDPOINTS (Handled locally for email)
# ===========================================

@app.route('/api/auth/register', methods=['POST'])
def handle_register():
    data = request.get_json()
    email = data.get('email', '')
    username = data.get('username', '')
    password = data.get('password', '')
    
    if not email or not username or not password:
        return jsonify({'error': 'All fields required'}), 400
    
    # Generate and send code instantly
    code = generate_verification_code()
    temp_codes[email] = {
        'code': code,
        'expires': datetime.utcnow() + timedelta(minutes=10)
    }
    
    if send_verification_email(email, code):
        # Forward to HF Space in background
        def forward():
            try:
                requests.post(
                    f"{HF_SPACE_URL}/api/auth/register",
                    json=data,
                    timeout=30
                )
            except:
                pass
        threading.Thread(target=forward, daemon=True).start()
        
        return jsonify({
            'success': True,
            'message': 'Verification code sent to your email',
            'email': email
        })
    else:
        return jsonify({'error': 'Failed to send verification email'}), 500

@app.route('/api/auth/verify', methods=['POST'])
def verify_code():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    
    if email not in temp_codes:
        return jsonify({'error': 'No verification code found'}), 400
    
    stored = temp_codes[email]
    if stored['expires'] < datetime.utcnow():
        del temp_codes[email]
        return jsonify({'error': 'Code has expired'}), 400
    
    if stored['code'] != code:
        return jsonify({'error': 'Invalid code'}), 400
    
    del temp_codes[email]
    
    # Forward to HF Space
    try:
        hf_response = requests.post(
            f"{HF_SPACE_URL}/api/auth/verify",
            json={'email': email, 'code': code},
            timeout=60
        )
        return Response(
            response=hf_response.content,
            status=hf_response.status_code,
            headers=dict(hf_response.headers)
        )
    except Exception as e:
        return jsonify({'error': 'Verification failed'}), 500

@app.route('/api/auth/resend-verification', methods=['POST'])
def resend_verification():
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({'error': 'Email required'}), 400
    
    code = generate_verification_code()
    temp_codes[email] = {
        'code': code,
        'expires': datetime.utcnow() + timedelta(minutes=10)
    }
    
    if send_verification_email(email, code):
        return jsonify({'success': True, 'message': 'New code sent'})
    else:
        return jsonify({'error': 'Failed to send email'}), 500

@app.route('/api/auth/reset-request', methods=['POST'])
def reset_request():
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({'error': 'Email required'}), 400
    
    code = generate_verification_code()
    temp_codes[f"reset_{email}"] = {
        'code': code,
        'expires': datetime.utcnow() + timedelta(minutes=10)
    }
    
    if send_password_reset_email(email, code):
        return jsonify({'success': True, 'message': 'Reset code sent'})
    else:
        return jsonify({'error': 'Failed to send email'}), 500

@app.route('/api/auth/verify-reset', methods=['POST'])
def verify_reset():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    
    key = f"reset_{email}"
    if key not in temp_codes:
        return jsonify({'error': 'Invalid code'}), 400
    
    stored = temp_codes[key]
    if stored['expires'] < datetime.utcnow():
        del temp_codes[key]
        return jsonify({'error': 'Code expired'}), 400
    
    if stored['code'] != code:
        return jsonify({'error': 'Invalid code'}), 400
    
    return jsonify({'success': True})

@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    new_password = data.get('new_password')
    
    key = f"reset_{email}"
    if key not in temp_codes:
        return jsonify({'error': 'Invalid code'}), 400
    
    stored = temp_codes[key]
    if stored['expires'] < datetime.utcnow():
        del temp_codes[key]
        return jsonify({'error': 'Code expired'}), 400
    
    if stored['code'] != code:
        return jsonify({'error': 'Invalid code'}), 400
    
    del temp_codes[key]
    
    try:
        hf_response = requests.post(
            f"{HF_SPACE_URL}/api/auth/reset-password",
            json={'email': email, 'new_password': new_password},
            timeout=60
        )
        return Response(
            response=hf_response.content,
            status=hf_response.status_code,
            headers=dict(hf_response.headers)
        )
    except Exception as e:
        return jsonify({'error': 'Password reset failed'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login_api():
    """Forward login to HF Space"""
    try:
        resp = requests.post(
            f"{HF_SPACE_URL}/api/auth/login",
            json=request.get_json(),
            timeout=60
        )
        return Response(
            response=resp.content,
            status=resp.status_code,
            headers=dict(resp.headers)
        )
    except Exception as e:
        return jsonify({'error': 'Login failed'}), 500

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """Forward status check to HF Space"""
    try:
        resp = requests.get(f"{HF_SPACE_URL}/api/auth/status", timeout=10)
        return Response(
            response=resp.content,
            status=resp.status_code,
            headers=dict(resp.headers)
        )
    except:
        return jsonify({'authenticated': False}), 200

@app.route('/api/auth/logout', methods=['POST'])
def logout_api():
    """Forward logout to HF Space"""
    try:
        resp = requests.post(f"{HF_SPACE_URL}/api/auth/logout", timeout=30)
        return Response(
            response=resp.content,
            status=resp.status_code,
            headers=dict(resp.headers)
        )
    except Exception as e:
        return jsonify({'success': True}), 200

# ===========================================
# PROXY FOR OTHER API REQUESTS
# ===========================================

@app.route('/api/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_api(path):
    """Proxy API requests to HF Space"""
    target_url = f"{HF_SPACE_URL}/api/{path}"
    
    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers={'Content-Type': 'application/json'},
            json=request.get_json() if request.method in ['POST', 'PUT'] else None,
            timeout=60
        )
        return Response(
            response=resp.content,
            status=resp.status_code,
            headers=dict(resp.headers)
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 503

# ===========================================
# STATIC FILES (CSS, JS, etc.)
# ===========================================

@app.route('/static/<path:path>')
def serve_static(path):
    """Proxy static files to HF Space"""
    try:
        resp = requests.get(f"{HF_SPACE_URL}/static/{path}", timeout=30)
        return Response(
            response=resp.content,
            status=resp.status_code,
            headers=dict(resp.headers)
        )
    except:
        return "Not found", 404

# ===========================================
# EMAIL HELPER FUNCTIONS
# ===========================================

def send_verification_email(email, code):
    subject = "HenAi - Email Verification Code"
    body = f"""Hello,

Your verification code for HenAi is:

🔐 {code}

This code will expire in 10 minutes.

Enter this code on the verification page to complete your registration.

If you didn't request this, please ignore this email.

Best regards,
HenAi Team
"""
    return send_email(email, subject, body)

def send_password_reset_email(email, code):
    subject = "HenAi - Password Reset Code"
    body = f"""Hello,

We received a request to reset your HenAi password.

Your password reset code is:

🔐 {code}

This code will expire in 10 minutes.

Enter this code on the password reset page to create a new password.

If you didn't request this, please ignore this email.

Best regards,
HenAi Team
"""
    return send_email(email, subject, body)

# ===========================================
# HEALTH CHECK
# ===========================================

@app.route('/health')
def health():
    return {"status": "ok", "email_configured": bool(MAIL_USERNAME)}

# ===========================================
# RUN
# ===========================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Proxy running on port {port}")
    print(f"📧 Email configured: {bool(MAIL_USERNAME)}")
    app.run(host='0.0.0.0', port=port, debug=False)
