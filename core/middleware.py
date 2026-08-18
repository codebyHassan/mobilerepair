import time
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib.auth import logout
from django.http import JsonResponse
from django.conf import settings
from .jwt_auth import decode_user_jwt, generate_user_jwt

class JWTSessionInactivityMiddleware:
    """
    Middleware that enforces a strict 30-minute session-wise JWT token expiration.
    If the user has been inactive for 30 minutes, their JWT token expires and
    they are automatically logged out and redirected to login with an expiration notice.
    For active users, the token is kept fresh on every user interaction.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_prefixes = [
            '/static/',
            '/media/',
            '/login/',
            '/logout/',
            '/admin/login/',
            '/admin/logout/',
        ]

    def __call__(self, request):
        path = request.path_info

        # Skip static, media, login and logout paths
        if any(path.startswith(prefix) for prefix in self.exempt_prefixes):
            return self.get_response(request)

        if request.user.is_authenticated:
            # Retrieve JWT token from Session, Cookie, or Authorization Header
            token = (
                request.session.get('jwt_token') or 
                request.COOKIES.get('access_token') or
                self._get_bearer_token(request)
            )

            # If user is authenticated but token is missing, generate a new one
            if not token:
                token = generate_user_jwt(request.user, session_key=request.session.session_key or '')
                request.session['jwt_token'] = token
                request.session.modified = True

            # Verify token validity and expiration
            payload = decode_user_jwt(token)

            if payload is None:
                # Token expired (30 minutes passed without activity)
                logout(request)
                if 'jwt_token' in request.session:
                    del request.session['jwt_token']
                request.session.flush()

                # Handle API request vs Page request
                if path.startswith('/api/') or request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
                    response = JsonResponse({
                        'status': 'error',
                        'code': 'SESSION_EXPIRED',
                        'message': 'Your session expired after 30 minutes of inactivity. Please log in again.'
                    }, status=401)
                    response.delete_cookie('access_token')
                    return response

                login_url = f"{reverse('login')}?expired=1"
                response = redirect(login_url)
                response.delete_cookie('access_token')
                return response

            # Token is valid -> User is active! Refresh token for rolling 30-min window
            # Refresh if more than 1 minute has elapsed since issuance
            now = int(time.time())
            if now - payload.get('iat', 0) > 60:
                token = generate_user_jwt(request.user, session_key=request.session.session_key or '')
                request.session['jwt_token'] = token
                request.session.modified = True

            request.jwt_token = token
            request.jwt_payload = payload

        response = self.get_response(request)

        # Set or refresh JWT access_token cookie if present
        if hasattr(request, 'jwt_token') and request.jwt_token and request.user.is_authenticated:
            response.set_cookie(
                'access_token',
                request.jwt_token,
                max_age=getattr(settings, 'JWT_EXPIRY_SECONDS', 1800),
                httponly=True,
                samesite='Lax',
                secure=not settings.DEBUG
            )

        return response

    def _get_bearer_token(self, request):
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            return auth_header.split(' ', 1)[1].strip()
        return None
