"""
HenAi Render Proxy - Email sent instantly, no waiting for HF Space
"""

from flask import Flask, request, Response, jsonify
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
import uuid

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

# Temporary storage for verification codes (in memory - resets on restart)
temp_codes = {}

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return ''.join(random.choices(string.digits, k=6))

def send_email(to_email, subject, body):
    """Send email using SMTP - runs instantly"""
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
        logger.info(f"✅ Email sent instantly to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False

# ===========================================
# REGISTRATION - EMAIL SENT IMMEDIATELY
# ===========================================

@app.route('/api/auth/register', methods=['POST'])
def handle_register():
    """Handle registration - send email instantly, then forward to HF Space"""
    data = request.get_json()
    email = data.get('email', '')
    username = data.get('username', '')
    password = data.get('password', '')
    
    if not email or not username or not password:
        return jsonify({'error': 'All fields required'}), 400
    
    # STEP 1: Generate code and send email IMMEDIATELY (no waiting)
    code = generate_verification_code()
    
    # Store code temporarily
    temp_codes[email] = {
        'code': code,
        'expires': datetime.utcnow() + timedelta(minutes=10)
    }
    
    # Send email instantly
    email_sent = send_verification_email(email, code)
    
    if not email_sent:
        return jsonify({'error': 'Failed to send verification email'}), 500
    
    # STEP 2: Forward to HF Space in background (don't wait for response)
    def forward_to_hf():
        try:
            requests.post(
                f"{HF_SPACE_URL}/api/auth/register",
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=60
            )
        except Exception as e:
            logger.error(f"HF Space forward error: {e}")
    
    # Start background thread (user doesn't wait for this)
    threading.Thread(target=forward_to_hf, daemon=True).start()
    
    # STEP 3: Return success immediately
    return jsonify({
        'success': True,
        'message': 'Verification code sent to your email',
        'email': email
    })

# ===========================================
# VERIFY CODE
# ===========================================

@app.route('/api/auth/verify', methods=['POST'])
def verify_code():
    """Verify the 6-digit code"""
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    
    if email not in temp_codes:
        return jsonify({'error': 'No verification code found. Please register again.'}), 400
    
    stored = temp_codes[email]
    if stored['expires'] < datetime.utcnow():
        del temp_codes[email]
        return jsonify({'error': 'Code has expired. Please request a new one.'}), 400
    
    if stored['code'] != code:
        return jsonify({'error': 'Invalid verification code'}), 400
    
    # Code verified - forward to HF Space to complete registration
    del temp_codes[email]
    
    try:
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
    except Exception as e:
        return jsonify({'error': 'Verification failed. Please try again.'}), 500

# ===========================================
# RESEND VERIFICATION CODE
# ===========================================

@app.route('/api/auth/resend-verification', methods=['POST'])
def resend_verification():
    """Resend verification code"""
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

# ===========================================
# PASSWORD RESET REQUEST
# ===========================================

@app.route('/api/auth/reset-request', methods=['POST'])
def reset_request():
    """Handle password reset request - send email instantly"""
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({'error': 'Email required'}), 400
    
    # Generate and send code instantly
    code = generate_verification_code()
    temp_codes[f"reset_{email}"] = {
        'code': code,
        'expires': datetime.utcnow() + timedelta(minutes=10)
    }
    
    if send_password_reset_email(email, code):
        return jsonify({'success': True, 'message': 'Reset code sent to your email'})
    else:
        return jsonify({'error': 'Failed to send reset email'}), 500

# ===========================================
# VERIFY RESET CODE
# ===========================================

@app.route('/api/auth/verify-reset', methods=['POST'])
def verify_reset():
    """Verify password reset code"""
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    
    key = f"reset_{email}"
    if key not in temp_codes:
        return jsonify({'error': 'Invalid or expired code'}), 400
    
    stored = temp_codes[key]
    if stored['expires'] < datetime.utcnow():
        del temp_codes[key]
        return jsonify({'error': 'Code has expired'}), 400
    
    if stored['code'] != code:
        return jsonify({'error': 'Invalid code'}), 400
    
    return jsonify({'success': True, 'message': 'Code verified'})

# ===========================================
# RESET PASSWORD
# ===========================================

@app.route('/api/auth/reset-password', methods=['POST'])
def reset_password():
    """Complete password reset"""
    data = request.get_json()
    email = data.get('email')
    code = data.get('code')
    new_password = data.get('new_password')
    
    key = f"reset_{email}"
    if key not in temp_codes:
        return jsonify({'error': 'Invalid or expired code'}), 400
    
    stored = temp_codes[key]
    if stored['expires'] < datetime.utcnow():
        del temp_codes[key]
        return jsonify({'error': 'Code has expired'}), 400
    
    if stored['code'] != code:
        return jsonify({'error': 'Invalid code'}), 400
    
    # Forward to HF Space
    del temp_codes[key]
    
    try:
        hf_response = requests.post(
            f"{HF_SPACE_URL}/api/auth/reset-password",
            json={'email': email, 'new_password': new_password},
            headers={'Content-Type': 'application/json'},
            timeout=60
        )
        return Response(
            response=hf_response.content,
            status=hf_response.status_code,
            headers=dict(hf_response.headers)
        )
    except Exception as e:
        return jsonify({'error': 'Password reset failed'}), 500

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
# PROXY FOR ALL OTHER REQUESTS
# ===========================================

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD'])
def proxy(path):
    """Forward all other requests to HF Space"""
    
    # Skip auth routes we handle
    if path in ['api/auth/register', 'api/auth/verify', 'api/auth/resend-verification', 
                'api/auth/reset-request', 'api/auth/verify-reset', 'api/auth/reset-password']:
        return Response('Not found', 404)
    
    target_url = f"{HF_SPACE_URL}/{path}" if path else HF_SPACE_URL
    
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
        return f"Error: {str(e)}", 503

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
