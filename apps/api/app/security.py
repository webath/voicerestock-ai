"""Άμυνα του App API — ένα σημείο, μία ASGI middleware.

Το API ακούει μόνο στο 127.0.0.1 (uvicorn default). Ο browser όμως του presenter μπορεί να ανοίξει οποιαδήποτε σελίδα,
και μια σελίδα μπορεί να στείλει αίτημα στο localhost. Γι' αυτό, σε κάθε αίτημα:

1. Host allowlist (κατά DNS rebinding): μόνο localhost / 127.0.0.1 (ο voice agent έρχεται από το SSH tunnel ως 127.0.0.1).
2. Origin allowlist: αν ο browser στέλνει Origin, πρέπει να είναι το dashboard. Server-to-server (voice agent) δεν στέλνει.
3. Anti-CSRF: κάθε εγγραφή (POST/PUT/PATCH/DELETE) θέλει header X-Actor — custom header ⇒ ο browser κάνει preflight,
   που μια ξένη σελίδα δεν περνά. Ο ίδιος header γράφεται στο audit log (ποιος έκανε τι).
4. Όριο μεγέθους σώματος αιτήματος (64 KB) — κανένα endpoint δεν χρειάζεται περισσότερα.
5. Όρια ρυθμού στα endpoints που κοστίζουν ή βγαίνουν προς τα έξω (SMS, LLM, ERP drafts).
6. Security headers σε κάθε απάντηση (nosniff, no-store, no-referrer, frame-ancestors none).

Ρυθμίσεις (.env): API_ALLOWED_HOSTS, WEB_ORIGINS — με ασφαλή defaults για το demo.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from collections import deque

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
MAX_BODY = 64 * 1024
ACTOR_RE = re.compile(r"^[\w.:@\-]{1,64}$")

# (μέθοδος, regex διαδρομής) → (αιτήματα, ανά δευτερόλεπτα). Ένας χρήστης τοπικά: παγκόσμια όρια ανά κανόνα.
RATE_LIMITS: list[tuple[str, re.Pattern, int, int]] = [
    ("POST", re.compile(r"^/api/campaigns/sms/send$"), 5, 60),            # SMS = χρήματα + πραγματικό κινητό
    ("POST", re.compile(r"^/api/campaigns/sms/draft$"), 20, 60),          # LLM
    ("POST", re.compile(r"^/api/assistant$"), 20, 60),                    # LLM
    ("POST", re.compile(r"^/api/suggestions/[^/]+/customer-message$"), 20, 60),
    ("POST", re.compile(r"^/api/suggestions/[^/]+/create-draft$"), 30, 60),  # γράφει στο ERP
    ("POST", re.compile(r"^/api/admin/reset$"), 3, 60),
    ("POST", re.compile(r"^/api/contacts/(import|clear)$"), 10, 60),      # μαζικές αλλαγές σε προσωπικά δεδομένα
    ("POST", re.compile(r"^/api/market/scan$"), 3, 60),                   # κάθε έρευνα κοστίζει
]

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
    (b"x-frame-options", b"DENY"),
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
    (b"cache-control", b"no-store"),
]


def _csv(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.environ.get(name, default).split(",") if x.strip()]


def allowed_hosts() -> list[str]:
    # «testserver» = το FastAPI TestClient· δεν υπάρχει ως πραγματικό όνομα.
    return _csv("API_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")


def allowed_origins() -> list[str]:
    return _csv("WEB_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")


class RateLimiter:
    def __init__(self):
        self.hits: dict[int, deque] = {}
        self.lock = threading.Lock()

    def check(self, method: str, path: str) -> int | None:
        """None = εντάξει· αλλιώς δευτερόλεπτα μέχρι να ξαναεπιτραπεί."""
        now = time.monotonic()
        for i, (m, rx, limit, window) in enumerate(RATE_LIMITS):
            if m != method or not rx.match(path):
                continue
            with self.lock:
                q = self.hits.setdefault(i, deque())
                while q and now - q[0] > window:
                    q.popleft()
                if len(q) >= limit:
                    return int(window - (now - q[0])) + 1
                q.append(now)
        return None


class SecurityMiddleware:
    def __init__(self, app, hosts: list[str] | None = None, origins: list[str] | None = None):
        self.app = app
        self.hosts = set(h.lower() for h in (hosts or allowed_hosts()))
        self.origins = set(origins or allowed_origins())
        self.limiter = RateLimiter()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        method, path = scope["method"], scope["path"]

        host = headers.get("host", "").lower()
        host = host[1:].split("]")[0] if host.startswith("[") else host.split(":")[0]
        if host not in self.hosts:
            return await _deny(send, 400, "bad_host", "μη επιτρεπτό Host")

        origin = headers.get("origin")
        if origin is not None and origin not in self.origins:
            return await _deny(send, 403, "bad_origin", "μη επιτρεπτή προέλευση")

        if method in WRITE_METHODS:
            if not ACTOR_RE.match(headers.get("x-actor", "")):
                return await _deny(send, 403, "missing_actor", "λείπει ή είναι άκυρος ο header X-Actor")
            try:
                if int(headers.get("content-length", "0") or 0) > MAX_BODY:
                    return await _deny(send, 413, "too_large", "πολύ μεγάλο αίτημα")
            except ValueError:
                return await _deny(send, 400, "bad_request", "άκυρο Content-Length")
            wait = self.limiter.check(method, path)
            if wait is not None:
                return await _deny(send, 429, "rate_limited", f"πάρα πολλά αιτήματα — ξαναδοκίμασε σε {wait}″",
                                   extra=[(b"retry-after", str(wait).encode())])
            receive = _capped(receive)

        extra = SECURITY_HEADERS if not path.startswith(("/docs", "/redoc", "/openapi")) else SECURITY_HEADERS[:3]

        async def send_with_headers(msg):
            if msg["type"] == "http.response.start":
                have = {k.lower() for k, _ in msg.get("headers", [])}
                msg["headers"] = list(msg.get("headers", [])) + [h for h in extra if h[0] not in have]
            await send(msg)

        return await self.app(scope, receive, send_with_headers)


def _capped(receive):
    """Κόβει σώματα χωρίς (ή με ψεύτικο) Content-Length πάνω από MAX_BODY."""
    seen = 0

    async def wrapped():
        nonlocal seen
        msg = await receive()
        if msg["type"] == "http.request":
            seen += len(msg.get("body", b""))
            if seen > MAX_BODY:
                raise ValueError("request body too large")
        return msg
    return wrapped


async def _deny(send, status: int, code: str, message: str, extra: list | None = None):
    body = json.dumps({"error": code, "message": message}, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                            *SECURITY_HEADERS, *(extra or [])]})
    await send({"type": "http.response.body", "body": body})
