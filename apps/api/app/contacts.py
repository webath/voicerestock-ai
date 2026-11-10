"""Επαφές πελατών (κινητό, email) — τα δεδομένα του ERP δεν τις έχουν, τις ανεβάζει ο χρήστης (CSV ή μία-μία).

- Αποθήκευση: data/processed/customer_contacts.json (gitignored — προσωπικά δεδομένα, ποτέ στο git).
- Λειτουργία SMS: «demo» (default) → ΟΛΑ τα SMS πάνε στο SMS_DEMO_TO· «live» → στο κινητό του ίδιου του πελάτη.
  Στο live ΔΕΝ υπάρχει σιωπηλή επιστροφή στο demo κινητό: πελάτης χωρίς κινητό = δεν στέλνεται.
- Τα κινητά δεν φεύγουν ποτέ ολόκληρα από το API (μόνο μασκαρισμένα) και ποτέ προς το LLM.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from .store import PROCESSED

FILE = PROCESSED / "customer_contacts.json"
MODES = ("demo", "live")
EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
MAX_ROWS = 5000
# Ονόματα στηλών που δεχόμαστε (πεζά, χωρίς κενά/τόνους δεν χρειάζεται — τα συνηθισμένα)
COLS = {
    "trdr": ("trdr", "id", "κωδικος_πελατη_id"),
    "code": ("code", "κωδικος", "κωδικός", "customer_code"),
    "phone": ("phone", "mobile", "κινητο", "κινητό", "τηλεφωνο", "τηλέφωνο", "tel"),
    "email": ("email", "e-mail", "mail"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_phone(raw: str) -> str | None:
    """Διεθνής μορφή χωρίς «+» (όπως τη θέλει το Apifon). «690 000 0522» → «306900000522». None = άκυρο."""
    d = re.sub(r"\D", "", raw or "")
    if d.startswith("00"):
        d = d[2:]
    if len(d) == 10 and d[0] in "62":                # ελληνικό κινητό/σταθερό χωρίς πρόθεμα χώρας
        d = "30" + d
    return d if 10 <= len(d) <= 15 and d[0] != "0" else None


def mask_phone(number: str | None) -> str | None:
    return f"+{number[:5]}•••{number[-4:]}" if number else None


class Contacts:
    def __init__(self, path: Path | None = None):
        self.path = path or FILE
        self.lock = threading.Lock()
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            self.data = {}
        self.data.setdefault("mode", "demo")
        self.data.setdefault("contacts", {})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(self.path)

    # ---------- ανάγνωση ----------
    @property
    def mode(self) -> str:
        return self.data["mode"]

    def get(self, trdr: int) -> dict:
        return self.data["contacts"].get(str(trdr), {})

    def phone(self, trdr: int) -> str | None:
        return self.get(trdr).get("phone")

    def email(self, trdr: int) -> str | None:
        return self.get(trdr).get("email")

    def summary(self, total_customers: int) -> dict:
        c = self.data["contacts"].values()
        return {"mode": self.mode, "total_customers": total_customers,
                "with_phone": sum(1 for x in c if x.get("phone")), "with_email": sum(1 for x in c if x.get("email"))}

    def public(self, trdr: int) -> dict:
        """Ό,τι επιτρέπεται να δει ο browser: κινητό μασκαρισμένο, email ολόκληρο (το χρειάζεται το mailto)."""
        c = self.get(trdr)
        return {"phone": mask_phone(c.get("phone")), "email": c.get("email"), "updated_at": c.get("updated_at")}

    # ---------- εγγραφή ----------
    def set_mode(self, mode: str) -> None:
        with self.lock:
            self.data["mode"] = mode
            self._save()

    def _put(self, trdr: int, phone: str | None, email: str | None, actor: str) -> None:
        key = str(trdr)
        if not phone and not email:
            self.data["contacts"].pop(key, None)
            return
        self.data["contacts"][key] = {"phone": phone, "email": email, "by": actor, "updated_at": _now()}

    def set(self, trdr: int, actor: str, **fields) -> dict:
        """Μία επαφή. Πεδίο που δεν δίνεται μένει ως έχει· κενό/None το σβήνει. ValueError με ελληνικό μήνυμα αν είναι άκυρο."""
        old = self.get(trdr)
        p, e = old.get("phone"), old.get("email")
        if "phone" in fields:
            raw = (fields["phone"] or "").strip()
            p = normalize_phone(raw) if raw else None
            if raw and not p:
                raise ValueError("άκυρο κινητό — γράψε το με 10 ψηφία (69…) ή με πρόθεμα χώρας (+30…)")
        if "email" in fields:
            e = (fields["email"] or "").strip().lower() or None
            if e and not EMAIL_RX.match(e):
                raise ValueError("άκυρο email")
        with self.lock:
            self._put(trdr, p, e, actor)
            self._save()
        return self.public(trdr)

    def clear(self) -> int:
        with self.lock:
            n = len(self.data["contacts"])
            self.data["contacts"] = {}
            self.data["mode"] = "demo"                       # χωρίς επαφές δεν έχει νόημα το live
            self._save()
            return n

    def import_csv(self, text: str, customers: dict[int, dict], actor: str) -> dict:
        """Upsert από CSV. Στήλες: TRDR ή CODE, και PHONE ή/και EMAIL (διαχωριστικό , ή ;). Οι άκυρες γραμμές
        αναφέρονται μία-μία και ΔΕΝ εισάγονται· οι υπόλοιπες μπαίνουν."""
        text = text.lstrip("﻿")
        first = text.splitlines()[0] if text.strip() else ""
        delim = ";" if first.count(";") > first.count(",") else ","
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        if not rows:
            raise ValueError("το αρχείο είναι κενό")
        if len(rows) > MAX_ROWS:
            raise ValueError(f"πάρα πολλές γραμμές (ως {MAX_ROWS})")
        head = [h.strip().lower() for h in rows[0]]
        idx = {k: next((head.index(n) for n in names if n in head), None) for k, names in COLS.items()}
        if idx["trdr"] is None and idx["code"] is None:
            raise ValueError("λείπει στήλη TRDR ή CODE για να βρεθεί ο πελάτης")
        if idx["phone"] is None and idx["email"] is None:
            raise ValueError("λείπει στήλη PHONE ή EMAIL")
        by_code = {str(c["CODE"]).strip(): t for t, c in customers.items()}
        cell = lambda r, k: (r[idx[k]].strip() if idx[k] is not None and idx[k] < len(r) else "")  # noqa: E731
        imported, errors, empty = 0, [], 0
        with self.lock:
            for n, r in enumerate(rows[1:], start=2):
                if not any(x.strip() for x in r):
                    continue
                trdr = None
                if cell(r, "trdr").isdigit() and int(cell(r, "trdr")) in customers:
                    trdr = int(cell(r, "trdr"))
                elif cell(r, "code") in by_code:
                    trdr = by_code[cell(r, "code")]
                if trdr is None:
                    errors.append({"row": n, "error": f"άγνωστος πελάτης «{cell(r, 'trdr') or cell(r, 'code')}»"})
                    continue
                raw_p, raw_e = cell(r, "phone"), cell(r, "email").lower()
                if not raw_p and not raw_e:
                    empty += 1                                  # γραμμή του προτύπου που δεν συμπληρώθηκε
                    continue
                p = normalize_phone(raw_p) if raw_p else None
                if raw_p and not p:
                    errors.append({"row": n, "error": f"άκυρο κινητό «{raw_p}»"})
                    continue
                if raw_e and not EMAIL_RX.match(raw_e):
                    errors.append({"row": n, "error": f"άκυρο email «{raw_e}»"})
                    continue
                old = self.get(trdr)                            # κενό πεδίο στο CSV δεν σβήνει ό,τι υπήρχε
                self._put(trdr, p or old.get("phone"), raw_e or old.get("email"), actor)
                imported += 1
            self._save()
        return {"imported": imported, "skipped_empty": empty, "errors": errors[:50], "error_count": len(errors)}
