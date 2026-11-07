"""Ενέργειες από τα Campaigns: αλλαγές τιμών/εκπτώσεων από τον χρήστη και SMS προσφοράς στον πελάτη (Apifon).

- Ο χρήστης αλλάζει το ποσοστό που προτείνει το σύστημα (αύξηση/μείωση τιμής, έκπτωση γιορτής) και το εγκρίνει.
  Αποθήκευση: data/processed/campaign_state.json — το ERP δεν έχει endpoint τιμών, οπότε η έγκριση μένει εδώ (+ audit).
- SMS: το κείμενο το γράφει το Claude ΜΟΝΟ από τα στοιχεία που του δίνουμε· αν βάλει αριθμό που δεν υπάρχει στα
  στοιχεία, ή ξεπεράσει τα 3 SMS, ή λείπει κλειδί → σταθερό πρότυπο. Η αποστολή γίνεται μόνο με κουμπί του χρήστη,
  με idempotency key (ένα πάτημα = ένα SMS).
- Τηλέφωνο: SMS_DEMO_TO (όλα τα SMS πάνε σε αυτό — demo) ή CUSTOMER_<TRDR>_PHONE. Τα δεδομένα της Revival δεν έχουν κινητά.
- Apifon: POST https://ars.apifon.com/services/api/v1/sms/send, υπογραφή HMAC-SHA256 (docs.apifon.com/authentication).
"""
from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import logging
import math
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable

import httpx

from .explain import _get_client
from .market import has_credentials
from .store import PROCESSED

log = logging.getLogger("outreach")
STATE_FILE = PROCESSED / "campaign_state.json"
MODEL = os.environ.get("SMS_MODEL", "claude-opus-5-5")
FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
MAX_SEGMENTS = 3
PRICE_LIMIT = 0.30          # ±30% — πάνω από αυτό είναι μάλλον λάθος πληκτρολόγησης
DISC_LIMIT = 50.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# ---------------- κατάσταση (αλλαγές χρήστη + ιστορικό SMS) ----------------
class CampaignState:
    def __init__(self, path=None):
        self.path = path or STATE_FILE
        self.lock = threading.Lock()
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {}
        for k in ("prices", "discounts", "sms"):
            self.data.setdefault(k, {} if k != "sms" else [])

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def set_price(self, mtrl: int, change_pct: float | None, status: str, actor: str) -> dict | None:
        with self.lock:
            if change_pct is None:
                self.data["prices"].pop(str(mtrl), None)
                rec = None
            else:
                rec = {"change_pct": round(change_pct, 4), "status": status, "by": actor, "at": _now()}
                self.data["prices"][str(mtrl)] = rec
            self._save()
            return rec

    def set_discount(self, event: str, mtrl: int, disc: float | None, actor: str) -> dict | None:
        key = f"{event}|{mtrl}"
        with self.lock:
            if disc is None:
                self.data["discounts"].pop(key, None)
                rec = None
            else:
                rec = {"disc": round(disc, 1), "by": actor, "at": _now()}
                self.data["discounts"][key] = rec
            self._save()
            return rec

    def sms_by_key(self, key: str) -> dict | None:
        return next((s for s in self.data["sms"] if s["idempotency_key"] == key), None)

    def add_sms(self, rec: dict) -> None:
        with self.lock:
            self.data["sms"].insert(0, rec)
            self.data["sms"] = self.data["sms"][:500]
            self._save()

    def save(self) -> None:
        with self.lock:
            self._save()

    def apply(self, report: dict) -> dict:
        """Η αναφορά των Campaigns με τις αλλαγές του χρήστη από πάνω (η πρόταση του συστήματος μένει δίπλα)."""
        r = copy.deepcopy(report)
        for p in r["pricing"]:
            p["suggested_change_pct"] = p["change_pct"]
            p["edit"] = self.data["prices"].get(str(p["MTRL"]))
            if p["edit"]:
                p["change_pct"] = p["edit"]["change_pct"]
        for e in r["seasonal"]:
            for it in e["items"]:
                it["suggested_disc_system"] = it["suggested_disc"]
                it["edit"] = self.data["discounts"].get(f"{e['event']}|{it['MTRL']}")
                if it["edit"]:
                    it["suggested_disc"] = it["edit"]["disc"]
        sent: dict[int, list] = {}
        for s in self.data["sms"]:
            if s["status"] == "sent":
                sent.setdefault(s["TRDR"], []).append({"kind": s["kind"], "MTRL": s.get("MTRL"), "at": s["at"]})
        r["sms_sent"] = {str(k): v for k, v in sent.items()}
        return r


# ---------------- τηλέφωνα ----------------
def _digits(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    return d[2:] if d.startswith("00") else d


def phone_for(trdr: int) -> tuple[str | None, str]:
    """(αριθμός Apifon χωρίς +, από πού ήρθε). Demo: όλα στο SMS_DEMO_TO."""
    demo = os.environ.get("SMS_DEMO_TO", "").strip()
    if demo:
        return _digits(demo), "demo"
    own = os.environ.get(f"CUSTOMER_{trdr}_PHONE", "").strip()
    return (_digits(own), "customer") if own else (None, "none")


def mask(number: str | None) -> str | None:
    return f"+{number[:5]}•••{number[-4:]}" if number else None


# ---------------- μήκος SMS (ελληνικά = UCS-2: 70 χαρ., 67 ανά κομμάτι όταν σπάει) ----------------
def segments(text: str) -> int:
    n = len(text)
    return 1 if n <= 70 else math.ceil(n / 67)


# ---------------- κείμενο SMS ----------------
def facts_for(kind: str, report: dict, trdr: int, mtrl: int | None, event: str | None) -> dict:
    """Τα ΜΟΝΑ στοιχεία που επιτρέπεται να χρησιμοποιήσει το μήνυμα. KeyError → 404."""
    if kind == "seasonal":
        ev = next(e for e in report["seasonal"] if e["event"] == event)
        it = next(i for i in ev["items"] if i["MTRL"] == mtrl)
        t = next(t for t in it["targets"] if t["TRDR"] == trdr)
        return {"kind": kind, "customer": t["CUSTOMER_NAME"], "salesman": t["SALESMAN_NAME"], "event": ev["event"].split(" & ")[0],
                "item": _item(it["ITEM_NAME"]), "discount_pct": _num(it["suggested_disc"]),
                "valid_from": _dm(it["promo_from"]), "valid_to": _dm(it["promo_to"])}
    if kind == "price_promo":
        p = next(p for p in report["pricing"] if p["MTRL"] == mtrl)
        if p["change_pct"] is None or p["change_pct"] >= 0:
            raise ValueError("η πρόταση τιμής δεν είναι μείωση/προσφορά")
        t = next(t for t in p["targets"] if t["TRDR"] == trdr)
        return {"kind": kind, "customer": t["CUSTOMER_NAME"], "salesman": t["SALESMAN_NAME"], "item": _item(p["ITEM_NAME"]),
                "discount_pct": _num(-p["change_pct"] * 100)}
    if kind == "winback":
        a = next(a for a in report["alerts"] if a["TRDR"] == trdr)
        return {"kind": kind, "customer": a["CUSTOMER_NAME"], "salesman": a["SALESMAN_NAME"],
                "items": [_item(i["ITEM_NAME"]) for i in a["items"][:2]], "lost_customer": a["kind"] == "lost"}
    raise ValueError(f"άγνωστο είδος SMS: {kind}")


def _num(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def _dm(iso: str) -> str:
    return f"{int(iso[8:10])}/{int(iso[5:7])}"


def _short(name: str) -> str:
    """«Ταβέρνα Δυόσμος Ι.Κ.Ε.» → «Ταβέρνα Δυόσμος»."""
    return re.sub(r"\s+(Α\.?Ε\.?|Ε\.?Π\.?Ε\.?|Ο\.?Ε\.?|Ε\.?Ε\.?|Ι\.?Κ\.?Ε\.?|Μ\.?Ε\.?Π\.?Ε\.?)$", "", name).strip()


def _item(name: str) -> str:
    """«Παγάκια 2kg κιβ. 10 σακ.» → «Παγάκια 2kg» — η συσκευασία δεν χρειάζεται στο SMS."""
    return re.sub(r"\s*κιβ\..*$", "", name).strip()


def _first(name: str | None) -> str:
    return (name or "").split()[0] if name else "DEMO ΔΙΑΝΟΜΕΣ"


def template(f: dict) -> str:
    who, by = _short(f["customer"]), _first(f.get("salesman"))
    if f["kind"] == "seasonal":
        return (f"{who}: για {f['event']} προσφορά -{f['discount_pct']}% στο «{f['item']}», "
                f"{f['valid_from']}-{f['valid_to']}. Απαντήστε ΝΑΙ να σας καλέσουμε. {by}, DEMO ΔΙΑΝΟΜΕΣ")
    if f["kind"] == "price_promo":
        return f"{who}: προσφορά -{f['discount_pct']}% στο «{f['item']}» για λίγες μέρες. Απαντήστε ΝΑΙ για παραγγελία. {by}, DEMO ΔΙΑΝΟΜΕΣ"
    items = " και ".join(f"«{i}»" for i in f["items"])
    return (f"{who}, μας λείψατε! Έχουμε ειδική τιμή για εσάς σε {items}. Να σας καλέσουμε; {by}, DEMO ΔΙΑΝΟΜΕΣ"
            if f["lost_customer"] else
            f"{who}: ειδική τιμή για εσάς σε {items}. Να σας καλέσουμε για λεπτομέρειες; {by}, DEMO ΔΙΑΝΟΜΕΣ")


SMS_SYSTEM = """Γράφεις ΕΝΑ σύντομο SMS προσφοράς στα ελληνικά, από έναν χονδρέμπορο (DEMO ΔΙΑΝΟΜΕΣ) προς επαγγελματία πελάτη του.
Κανόνες:
- Το πολύ 190 χαρακτήρες συνολικά. Φιλικό, επαγγελματικό, χωρίς emoji, χωρίς link.
- Χρησιμοποίησε ΜΟΝΟ τα στοιχεία που σου δίνονται. Μην προσθέσεις ποσοστά, τιμές, ημερομηνίες ή ποσότητες που δεν υπάρχουν εκεί.
  Αν το `discount_pct` υπάρχει, γράψε το ακριβώς έτσι (π.χ. -8%).
- Ξεκίνα με το όνομα του πελάτη (χωρίς Α.Ε./Ι.Κ.Ε. κ.λπ.). Κλείσε με το μικρό όνομα του πωλητή και «DEMO ΔΙΑΝΟΜΕΣ».
- Ζήτα μια εύκολη απάντηση (π.χ. «Απαντήστε ΝΑΙ να σας καλέσουμε»).
- winback με lost_customer=true: ζεστό «μας λείψατε», χωρίς να κατηγορείς. Χωρίς ποσοστό αν δεν δίνεται."""
SMS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["text"], "properties": {"text": {"type": "string"}}}


def _numbers_ok(text: str, f: dict) -> bool:
    allowed = set(re.findall(r"\d+", json.dumps(f, ensure_ascii=False)))
    return set(re.findall(r"\d+", text)) <= allowed


def generate(f: dict, client_factory: Callable | None = None) -> tuple[str, str]:
    """(κείμενο, «ai» | «template»). Κάθε αποτυχία → πρότυπο, ποτέ λάθος προς τον χρήστη."""
    fallback = template(f)
    if not has_credentials():
        return fallback, "template"
    try:
        client = (client_factory or _get_client)()
        r = client.beta.messages.create(
            model=MODEL, max_tokens=1024, system=SMS_SYSTEM,
            messages=[{"role": "user", "content": json.dumps(f, ensure_ascii=False)}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SMS_SCHEMA}}, **FALLBACK)
        if r.stop_reason in ("refusal", "max_tokens"):
            return fallback, "template"
        text = " ".join(json.loads(next(b.text for b in r.content if b.type == "text"))["text"].split())
        if not text or segments(text) > MAX_SEGMENTS or not _numbers_ok(text, f):
            log.warning("sms text rejected (len=%s): %s", len(text), text)
            return fallback, "template"
        return text, "ai"
    except Exception as e:
        log.warning("sms generation failed: %s", e)
        return fallback, "template"


# ---------------- Apifon ----------------
class ApifonError(Exception):
    pass


class Apifon:
    BASE = "https://ars.apifon.com"
    PATH = "/services/api/v1/sms/send"

    def __init__(self, token: str | None = None, secret: str | None = None, sender: str | None = None,
                 post: Callable | None = None, base: str | None = None):
        self.token = token if token is not None else os.environ.get("APIFON_TOKEN", "")
        self.secret = secret if secret is not None else os.environ.get("APIFON_SECRET", "")
        self.sender = (sender if sender is not None else os.environ.get("APIFON_SENDER", "")) or "VORA"
        self.base = base or os.environ.get("APIFON_BASE_URL", self.BASE)
        self.post = post or (lambda url, content, headers: httpx.post(url, content=content, headers=headers, timeout=15))

    @property
    def configured(self) -> bool:
        return bool(self.token and self.secret)

    def sign(self, body: str, date: str) -> str:
        to_sign = f"POST\n{self.PATH}\n{body}\n{date}"
        mac = hmac.new(self.secret.encode("utf-8"), to_sign.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(mac).decode()

    def send(self, number: str, text: str, reference: str) -> dict:
        if not self.configured:
            raise ApifonError("Λείπουν τα στοιχεία Apifon (APIFON_TOKEN, APIFON_SECRET στο .env).")
        body = json.dumps({"subscribers": [{"number": number}], "reference_id": reference[:255],
                           "message": {"text": text, "dc": 2, "sender_id": self.sender[:11]}}, ensure_ascii=False)
        date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        headers = {"Content-Type": "application/json; charset=utf-8", "X-ApifonWS-Date": date,
                   "Authorization": f"ApifonWS {self.token}:{self.sign(body, date)}"}
        try:
            r = self.post(self.base + self.PATH, body.encode("utf-8"), headers)
        except httpx.HTTPError as e:
            raise ApifonError(f"Δεν υπάρχει σύνδεση με το Apifon ({type(e).__name__}).") from e
        try:
            data = r.json()
        except ValueError:
            data = {}
        info = data.get("result_info") or {}
        if r.status_code >= 400 or str(info.get("status_code", "200")) != "200":
            title = data.get("title") or info.get("description") or f"HTTP {r.status_code}"
            raise ApifonError(f"Το Apifon απέρριψε το SMS: {title}")
        res = (data.get("results") or {}).get(number) or [{}]
        return {"request_id": data.get("request_id"), "message_id": res[0].get("message_id")}


def new_sms_record(kind: str, trdr: int, mtrl: int | None, event: str | None, number: str, source: str,
                   text: str, actor: str, key: str) -> dict:
    return {"id": f"SMS-{uuid.uuid4().hex[:10]}", "idempotency_key": key, "kind": kind, "TRDR": trdr, "MTRL": mtrl,
            "event": event, "to": mask(number), "phone_source": source, "text": text, "segments": segments(text),
            "by": actor, "at": _now(), "status": "sending"}
