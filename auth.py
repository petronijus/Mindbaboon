"""Google OAuth login + session-based UI auth.

Flow: user hits a protected UI route → require_login decorator redirects to
/login → user clicks "Sign in with Google" → Authlib does authorization code
flow with PKCE → /oauth2/callback verifies id_token, enforces ALLOWED_EMAILS,
sets session['user']. API endpoints (api.py) keep their independent X-API-Key
auth and are CSRF-exempt at the app level.
"""
from __future__ import annotations

import logging
import os
from functools import wraps
from typing import Callable

from authlib.integrations.flask_client import OAuth
from flask import (
    Blueprint,
    Flask,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()


def init_oauth(app: Flask) -> None:
    """Register the Google OAuth client on `app`. Call once at startup."""
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError(
            "GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET must be set"
        )
    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile",
            "code_challenge_method": "S256",  # PKCE
        },
    )


def _allowed_emails() -> frozenset[str]:
    raw = os.environ.get("ALLOWED_EMAILS", "")
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


def require_login(view: Callable) -> Callable:
    """Redirect to /login if no session['user']. Preserves `next` for round-trip.

    Use on UI routes only. API routes use require_api_key in api.py.
    """

    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login_page", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapper


def _safe_next(target: str | None) -> str:
    """Only allow same-origin relative redirects after login."""
    if not target or not target.startswith("/") or target.startswith("//"):
        return url_for("index")
    return target


@auth_bp.route("/login", methods=["GET"])
def login_page():
    if "user" in session:
        return redirect(_safe_next(request.args.get("next")))
    return render_template("login.html", next=request.args.get("next", ""))


@auth_bp.route("/login/google", methods=["GET"])
def login_google():
    # Preserve where the user wanted to go before the OAuth redirect.
    session["post_login_redirect"] = _safe_next(request.args.get("next"))
    redirect_uri = url_for("auth.callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/oauth2/callback", methods=["GET"])
def callback():
    from flask import current_app

    limiter = current_app.extensions.get("limiter")
    if limiter:
        # Imperative rate limit: 10 callbacks/min per IP. Defense against
        # OAuth code replay / brute-force.
        try:
            limiter.limit("10/minute")(lambda: None)()
        except Exception:
            pass

    try:
        token = oauth.google.authorize_access_token()
    except Exception as exc:
        logger.warning("oauth_callback_failed: %s", exc)
        flash("Sign-in failed. Try again.", "error")
        return redirect(url_for("auth.login_page"))

    userinfo = token.get("userinfo") or oauth.google.parse_id_token(token, nonce=None)
    email = str(userinfo.get("email", "")).lower().strip()
    email_verified = bool(userinfo.get("email_verified"))
    name = str(userinfo.get("name") or email)

    if not email:
        logger.warning("oauth_callback_no_email")
        flash("Google did not return an email.", "error")
        return redirect(url_for("auth.login_page"))
    if not email_verified:
        logger.warning("oauth_callback_email_not_verified email=%s", email)
        flash("Email not verified by Google.", "error")
        return redirect(url_for("auth.login_page"))
    if email not in _allowed_emails():
        logger.warning("oauth_callback_email_not_allowed email=%s", email)
        flash("This email is not allowed to access Mindbaboon.", "error")
        return redirect(url_for("auth.login_page"))

    # Session fixation prevention: drop old session before setting new identity.
    target = session.pop("post_login_redirect", None) or url_for("index")
    session.clear()
    session["user"] = {"email": email, "name": name}
    session.permanent = True
    logger.info("login_success email=%s", email)
    return redirect(_safe_next(target))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    email = (session.get("user") or {}).get("email", "?")
    session.clear()
    logger.info("logout email=%s", email)
    return redirect(url_for("auth.login_page"))
