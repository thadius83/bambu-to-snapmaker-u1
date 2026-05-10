"""Security headers, CSP composition, and privacy-page conditional rendering.

Kept separate from main.py to keep the FastAPI entrypoint focused on routing,
and so the 500/1000-line cap on main.py has headroom.

The CSP is composed once at import time from env vars — adding a new
third-party origin means adding it here and updating .env.example.

Known console warning on CF-proxied sites: Cloudflare's JavaScript Detections
injects an inline script keyed to the CF-Ray ID. The hash rotates per-request
so it cannot be whitelisted. Accepted — no user impact, network-layer CF
protection (DDoS/WAF) is unaffected.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path

GA_MEASUREMENT_ID: str = os.environ.get("GA_MEASUREMENT_ID", "").strip()
CF_BEACON_TOKEN: str = os.environ.get("CF_BEACON_TOKEN", "").strip()

_FRONTEND_DIST = Path(os.environ.get("U13MF_FRONTEND_DIST", "/app/frontend/dist"))
_JSON_LD_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL
)


def _json_ld_hash() -> str | None:
    """Compute sha256 of the built JSON-LD block so Chrome doesn't block it.

    The hash changes when VITE_SITE_URL changes because the JSON-LD embeds the
    canonical URL. Reading the built index.html at startup keeps this in sync
    without a separate build step.
    """
    index = _FRONTEND_DIST / "index.html"
    try:
        html = index.read_text(encoding="utf-8")
    except OSError:
        return None
    m = _JSON_LD_RE.search(html)
    if not m:
        return None
    return _script_sha256(m.group(1))


def _google_tag_bootstrap_script(measurement_id: str) -> str:
    return "\n".join([
        "window.dataLayer=window.dataLayer||[];",
        "function gtag(){dataLayer.push(arguments);}",
        "gtag('js',new Date());",
        f"gtag('config',{json.dumps(measurement_id)});",
    ])


def _script_sha256(script: str) -> str:
    digest = hashlib.sha256(script.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def _build_csp() -> str:
    script_src = ["'self'"]
    # Whitelist the JSON-LD structured-data block — some Chrome versions apply
    # script-src to <script type="application/ld+json"> elements.
    json_ld = _json_ld_hash()
    if json_ld:
        script_src.append(json_ld)
    img_src = ["'self'", "data:"]
    connect_src = ["'self'"]

    if GA_MEASUREMENT_ID:
        script_src.append("https://*.googletagmanager.com")
        script_src.append(_script_sha256(_google_tag_bootstrap_script(GA_MEASUREMENT_ID)))
        img_src += ["https://*.google-analytics.com", "https://*.googletagmanager.com"]
        connect_src += [
            "https://*.google-analytics.com",
            "https://*.analytics.google.com",
            "https://*.googletagmanager.com",
        ]

    if CF_BEACON_TOKEN:
        script_src.append("https://static.cloudflareinsights.com")
        connect_src.append("https://cloudflareinsights.com")

    return "; ".join([
        "default-src 'self'",
        "script-src " + " ".join(script_src),
        "style-src 'self' 'unsafe-inline'",
        "img-src " + " ".join(img_src),
        "connect-src " + " ".join(connect_src),
        "font-src 'self'",
        "frame-src 'none'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ])


SECURITY_HEADERS: dict[str, str] = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Content-Security-Policy": _build_csp(),
}


_GA_SECTION_RE = re.compile(r"<!--BEGIN_GA_SECTION-->.*?<!--END_GA_SECTION-->", re.DOTALL)
_CF_SECTION_RE = re.compile(r"<!--BEGIN_CF_SECTION-->.*?<!--END_CF_SECTION-->", re.DOTALL)


def render_privacy_html(html: str) -> str:
    """Strip GA / CF blocks from the privacy template when their env vars are unset.

    Keeps the privacy policy honest for self-hosters who run with tracking off —
    they don't see claims about services they aren't using.
    """
    if not GA_MEASUREMENT_ID:
        html = _GA_SECTION_RE.sub("", html)
    if not CF_BEACON_TOKEN:
        html = _CF_SECTION_RE.sub("", html)
    return html
