import time
import json
import base64
import hmac
import hashlib
from django.conf import settings
from django.contrib.auth.models import User

JWT_SECRET = getattr(settings, 'SECRET_KEY', 'django-insecure-secret')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_SECONDS = getattr(settings, 'JWT_EXPIRY_SECONDS', 1800)  # 30 minutes

try:
    import jwt
    HAS_PYJWT = True
except ImportError:
    HAS_PYJWT = False

def _b64_encode(data_bytes):
    return base64.urlsafe_b64encode(data_bytes).decode('utf-8').rstrip('=')

def _b64_decode(data_str):
    padding = 4 - (len(data_str) % 4)
    if padding != 4:
        data_str += '=' * padding
    return base64.urlsafe_b64decode(data_str.encode('utf-8'))

def generate_user_jwt(user, session_key='', expiry_seconds=None):
    """
    Generate a signed JWT token with 30 minutes expiration (session-wise).
    Works seamlessly with PyJWT or pure-Python HMAC-SHA256 fallback.
    """
    if expiry_seconds is None:
        expiry_seconds = JWT_EXPIRY_SECONDS
    now = int(time.time())
    payload = {
        'user_id': user.id,
        'username': user.username,
        'is_superuser': user.is_superuser,
        'session_key': session_key or '',
        'iat': now,
        'exp': now + expiry_seconds,
    }
    
    if HAS_PYJWT:
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    # Pure Python zero-dependency HS256 JWT generator
    header = {'typ': 'JWT', 'alg': 'HS256'}
    header_b64 = _b64_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
    payload_b64 = _b64_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    signature = hmac.new(JWT_SECRET.encode('utf-8'), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64_encode(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def decode_user_jwt(token):
    """
    Verify and decode the JWT token. Returns payload dict or None if expired/invalid.
    Works seamlessly with PyJWT or pure-Python HMAC-SHA256 fallback.
    """
    if not token:
        return None
    
    if HAS_PYJWT:
        try:
            return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except Exception:
            return None
    
    # Pure Python zero-dependency HS256 JWT decoder & verifier
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
        expected_sig = hmac.new(JWT_SECRET.encode('utf-8'), signing_input, hashlib.sha256).digest()
        actual_sig = _b64_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64_decode(payload_b64).decode('utf-8'))
        if 'exp' in payload and int(time.time()) > payload['exp']:
            return None
        return payload
    except Exception:
        return None

def verify_token_and_get_user(token):
    """
    Verify the token and return the User instance along with the payload.
    """
    payload = decode_user_jwt(token)
    if not payload:
        return None, None
    try:
        user = User.objects.get(id=payload.get('user_id'), is_active=True)
        return user, payload
    except User.DoesNotExist:
        return None, None
