"""
HenAi Render Proxy - Complete backend with email and authentication
Email sending happens here (bypasses HF Spaces SMTP restrictions)
"""

from flask import Flask, request, Response, session, jsonify, redirect, url_for
from flask_cors import CORS
import requests
import os
import threading
import time
import logging
import smtplib
import random
import string
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import secrets
import urllib.parse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ===========================================
# CONFIGURATION
# ===========================================

app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

CORS(app, supports_credentials=True)

# Your Hugging Face Space URL
HF_SPACE_URL = os.environ.get('HF_SPACE_URL', 'https://henley2035-henai.hf.space')
HF_SPACE_URL = HF_SPACE_URL.rstrip('/')

# Keep-alive interval
KEEP_ALIVE_INTERVAL = int(os.environ.get('KEEP_ALIVE_INTERVAL', 240))

# ===========================================
# EMAIL CONFIGURATION (Gmail SMTP)
# ===========================================

MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() in ['true', 'on', '1']
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)

# ===========================================
# EMAIL FUNCTIONS (Run on Render, not HF Space)
# ===========================================

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return ''.join(random.choices(string.digits, k=6))

def send_email(to_email, subject, body):
    """Send email using SMTP (runs on Render)"""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        logger.warning("Email not configured - skipping")
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
        logger.error(f"Email send error: {e}")
        return False

def send_verification_email(email, code):
    """Send verification code email"""
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
    """Send password reset code email"""
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
# PROXY ENDPOINTS (Forward to HF Space)
# ===========================================

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD'])
def proxy(path):
    """Forward requests to HF Space"""
    
    # Skip API routes that we handle locally
    if path.startswith('api/auth/register') or path.startswith('api/auth/reset-request'):
        return handle_auth_request(request, path)
    
    # Build target URL
    if path:
        target_url = f"{HF_SPACE_URL}/{path}"
    else:
        target_url = HF_SPACE_URL
    
    # Prepare headers
    headers = {}
    for key, value in request.headers.items():
        key_lower = key.lower()
        if key_lower not in ['host', 'content-length', 'content-encoding']:
            headers[key] = value
    
    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            timeout=120,
            allow_redirects=True
        )
        
        return Response(
            response=resp.content,
            status=resp.status_code,
            headers=dict(resp.headers)
        )
        
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return f"Error connecting to HenAi. Please wait a moment. ({str(e)})", 503

# ===========================================
# LOCAL AUTH ENDPOINTS (Email handling on Render)
# ===========================================

def handle_auth_request(req, path):
    """Handle authentication requests locally for email sending"""
    try:
        data = req.get_json()
        
        if path == 'api/auth/register':
            # Forward registration to HF Space first
            hf_response = requests.post(
                f"{HF_SPACE_URL}/api/auth/register",
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=60
            )
            
            if hf_response.status_code == 200:
                hf_data = hf_response.json()
                if hf_data.get('success') and hf_data.get('email'):
                    # Send verification email from Render
                    code = generate_verification_code()
                    
                    # Store code temporarily (in memory - for demo)
                    # In production, use Redis or database
                    if not hasattr(app, 'temp_codes'):
                        app.temp_codes = {}
                    app.temp_codes[hf_data['email']] = {
                        'code': code,
                        'expires': datetime.utcnow() + timedelta(minutes=10)
                    }
                    
                    if send_verification_email(hf_data['email'], code):
                        return jsonify(hf_data)
                    else:
                        return jsonify({'error': 'Failed to send verification email'}), 500
            
            return jsonify(hf_response.json()), hf_response.status_code
        
        elif path == 'api/auth/reset-request':
            email = data.get('email')
            if email:
                code = generate_verification_code()
                
                if not hasattr(app, 'temp_codes'):
                    app.temp_codes = {}
                app.temp_codes[email] = {
                    'code': code,
                    'expires': datetime.utcnow() + timedelta(minutes=10)
                }
                
                if send_password_reset_email(email, code):
                    return jsonify({'success': True, 'message': 'Reset code sent'})
            
            return jsonify({'success': True, 'message': 'If an account exists, a reset code will be sent'})
        
        else:
            # Forward other auth requests to HF Space
            resp = requests.request(
                method=request.method,
                url=f"{HF_SPACE_URL}/{path}",
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=60
            )
            return Response(
                response=resp.content,
                status=resp.status_code,
                headers=dict(resp.headers)
            )
            
    except Exception as e:
        logger.error(f"Auth handler error: {e}")
        return jsonify({'error': str(e)}), 500

# ===========================================
# VERIFICATION ENDPOINTS (Local)
# ===========================================

@app.route('/api/auth/verify', methods=['POST'])
def verify_code():
    """Verify the 6-digit code (handled on Render)"""
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    
    if not hasattr(app, 'temp_codes') or email not in app.temp_codes:
        return jsonify({'error': 'Invalid or expired code'}), 400
    
    stored = app.temp_codes[email]
    if stored['expires'] < datetime.utcnow():
        del app.temp_codes[email]
        return jsonify({'error': 'Code has expired'}), 400
    
    if stored['code'] != code:
        return jsonify({'error': 'Invalid code'}), 400
    
    # Code verified - forward to HF Space to complete registration
    del app.temp_codes[email]
    
    # Forward to HF Space to mark user as verified
    hf_response = requests.post(
        f"{HF_SPACE_URL}/api/auth/verify",
        json={'email': email, 'code': code},
        headers={'Content-Type': 'application/json'},
        timeout=60
    )
    
    return Response(
        response=hf_response.content,
        status=hf_response.status_code,
        headers=dict(hf_response.headers)
    )

@app.route('/api/auth/resend-verification', methods=['POST'])
def resend_verification():
    """Resend verification code"""
    data = request.get_json()
    email = data.get('email')
    
    if email:
        code = generate_verification_code()
        
        if not hasattr(app, 'temp_codes'):
            app.temp_codes = {}
        app.temp_codes[email] = {
            'code': code,
            'expires': datetime.utcnow() + timedelta(minutes=10)
        }
        
        if send_verification_email(email, code):
            return jsonify({'success': True, 'message': 'Code resent'})
    
    return jsonify({'error': 'Failed to resend code'}), 500

# ===========================================
# HEALTH CHECK
# ===========================================

@app.route('/health')
def health():
    """Health check endpoint"""
    return {"status": "ok", "proxy_to": HF_SPACE_URL, "email_configured": bool(MAIL_USERNAME)}

# ===========================================
# KEEP-ALIVE
# ===========================================

def keep_alive():
    """Background thread to keep the space warm"""
    while True:
        try:
            response = requests.get(HF_SPACE_URL, timeout=30)
            if response.status_code == 200:
                logger.info(f"💓 Keep-alive ping successful to {HF_SPACE_URL}")
            else:
                logger.warning(f"⚠️ Keep-alive ping got status {response.status_code}")
        except Exception as e:
            logger.warning(f"Keep-alive ping failed: {e}")
        time.sleep(KEEP_ALIVE_INTERVAL)

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

# ===========================================
# RUN
# ===========================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Render Proxy running on port {port}")
    logger.info(f"📍 Forwarding to: {HF_SPACE_URL}")
    logger.info(f"📧 Email configured: {bool(MAIL_USERNAME)}")
    app.run(host='0.0.0.0', port=port, debug=False)
