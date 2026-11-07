#!/usr/bin/env python3
"""Mock App API (stdlib only) — ίδια endpoints με το docs/CONTRACTS.md, πάνω στο fixtures/suggestions.sample.json.

Για να δουλεύει ο voice agent / το dashboard πριν υπάρξει το πραγματικό apps/api.
Τα create-draft γράφονται ΠΡΑΓΜΑΤΙΚΑ στο mock ERP (ERP_BASE_URL, default http://localhost:8080).

    python3 scripts/mock_app_api.py [--port 8000]
"""
import argparse, copy, hashlib, json, os, re, secrets, time, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, 'fixtures', 'suggestions.sample.json')
ERP = os.environ.get('ERP_BASE_URL', 'http://localhost:8080').rstrip('/')
URG = {'high': 0, 'medium': 1, 'low': 2}

LOCK = Lock()
def _seed(): return {s['id']: s for s in json.load(open(FIXTURE, encoding='utf-8'))['suggestions']}
SUGS = _seed()
TOKENS = {}      # token -> (suggestion_id, version)
IDEMP = {}       # idempotency_key -> response
CALLS = {}       # call_sid -> Call
AUDIT = []


def _rd(name):
    import csv
    with open(os.path.join(ROOT, 'team_pack', 'data', name), encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def load_history():
    """Καθαρή ποσότητα ανά (TRDR, MTRL, ημέρα): χωρίς ακυρωμένα & υπηρεσίες, πιστωτικά αρνητικά, free goods μέσα."""
    items = {r['MTRL']: r for r in _rd('MTRL.csv')}
    heads = {h['FINDOC']: h for h in _rd('SALDOC.csv') if h['ISCANCEL'] == '0'}
    hist = {}
    for l in _rd('MTRLINES.csv'):
        h = heads.get(l['FINDOC'])
        if not h or items[l['MTRL']]['MTRTYPE'] != '0': continue
        q = float(l['QTY1']) * (-1 if h['SERIES'] == '7071' else 1)
        d = hist.setdefault(int(h['TRDR']), {}).setdefault(int(l['MTRL']), {})
        d[h['TRNDATE']] = d.get(h['TRNDATE'], 0) + q
    return items, hist


ITEMS, HISTORY = load_history()
SALESMEN = {int(r['PRSN']): r['NAME'] for r in _rd('PRSN.csv')}
# «Σήμερα» του σεναρίου (README: «Σήμερα είναι 1/11/2026»). Από εδώ μετράει το days_left του /api/risk.
TODAY = os.environ.get('SCENARIO_TODAY', '2026-11-01')
TARGETS = {}
for r in _rd('prediction_targets.csv'): TARGETS.setdefault(int(r['TRDR']), []).append(int(r['MTRL']))

MOCK_EVALUATION = {'source': 'MOCK — όχι πραγματικά αποτελέσματα', 'cutoffs': ['2026-08-01'],
                   'rows': [{'model': 'cutoff+30 (README)', 'mae': 18.3, 'within_3': None, 'within_7': None, 'at_risk_precision': None, 'at_risk_recall': None},
                            {'model': 'baseline 180d (README)', 'mae': 16.1, 'within_3': None, 'within_7': None, 'at_risk_precision': None, 'at_risk_recall': None}]}


def mock_explanation(s):
    parts = []
    for l in s['LINES']:
        e = l['evidence']
        t = (f"{l['ITEM_NAME']}: καταναλώνει περίπου {e['burn_rate_per_day']} {l['UNIT']} τη μέρα, τελευταία παραλαβή "
             f"{e['last_purchase_qty']} {l['UNIT']} στις {e['last_purchase_date']}, άρα εκτιμάται εξάντληση γύρω στις {l['PREDICTED_DEPLETION_DATE']}.")
        if e.get('promo'): t += f" Ισχύει {e['promo']['name']} ({e['promo']['from']} έως {e['promo']['to']})."
        if e.get('cold_start'): t += f" Νέος πελάτης — η πρόβλεψη βασίζεται σε παρόμοιους ({e['peer_group']})."
        parts.append(t)
    return {'text': '[MOCK, χωρίς LLM] ' + ' '.join(parts), 'grounded_on': ['burn_rate_per_day', 'last_purchase_qty', 'last_purchase_date', 'promo', 'cold_start']}


def now(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def days_between(a, b):
    if not b: return None
    from datetime import date
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def audit(actor, action, sid, outcome):
    AUDIT.append({'at': now(), 'actor': actor, 'action': action, 'suggestion_id': sid, 'outcome': outcome})
    print(f"[audit] {actor} {action} {sid} -> {outcome}")


def erp_payload(s):
    return {'TRDR': s['TRDR'], 'CUSTOMER_CODE': s['CUSTOMER_CODE'], 'SALESMAN': s['SALESMAN'],
            'SUGGESTED_DELIVERY_DATE': s['SUGGESTED_DELIVERY_DATE'], 'REASON': s['REASON'],
            'LINES': [{k: l[k] for k in ('MTRL', 'ITEM_CODE', 'QTY1', 'PREDICTED_DEPLETION_DATE', 'CONFIDENCE')} for l in s['LINES']]}


def post_erp(body):
    req = urllib.request.Request(ERP + '/api/draft-orders', data=json.dumps(body, ensure_ascii=False).encode(),
                                 headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=10) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b'{}')
    except Exception as e: return 502, {'errors': [f'ERP unreachable: {e}']}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

    def err(self, code, e, msg): return self.send(code, {'error': e, 'message': msg})

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in (('Access-Control-Allow-Origin', '*'), ('Access-Control-Allow-Methods', 'GET,POST,OPTIONS'),
                     ('Access-Control-Allow-Headers', 'Content-Type,X-Actor')): self.send_header(k, v)
        self.end_headers()

    def body(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        return json.loads(self.rfile.read(n) or b'{}') if n else {}

    def do_GET(self):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}; p = u.path.rstrip('/')
        if p == '/api/health': return self.send(200, {'ok': True, 'mock': True})
        if p == '/api/salesmen':
            return self.send(200, [{'PRSN': i, 'NAME': n, 'phone': os.environ.get(f'SALESMAN_{i}_PHONE')}
                                   for i, n in sorted(SALESMEN.items())])
        if p == '/api/suggestions':
            rows = [s for s in SUGS.values()
                    if ('salesman' not in q or str(s['SALESMAN']) == q['salesman']) and ('status' not in q or s['status'] == q['status'])]
            return self.send(200, sorted(rows, key=lambda s: (URG[s['urgency']], s['SUGGESTED_DELIVERY_DATE'])))
        if p == '/api/risk':
            rows = [{'TRDR': s['TRDR'], 'CUSTOMER_NAME': s['CUSTOMER_NAME'], 'SALESMAN': s['SALESMAN'], 'MTRL': l['MTRL'],
                     'ITEM_NAME': l['ITEM_NAME'], 'PREDICTED_DEPLETION_DATE': l['PREDICTED_DEPLETION_DATE'],
                     'days_left': days_between(TODAY, l['PREDICTED_DEPLETION_DATE']),
                     'CONFIDENCE': l['CONFIDENCE'], 'urgency': s['urgency'], 'suggestion_id': s['id']}
                    for s in SUGS.values() for l in s['LINES'] if 'salesman' not in q or str(s['SALESMAN']) == q['salesman']]
            rows.sort(key=lambda r: r['PREDICTED_DEPLETION_DATE'])
            return self.send(200, rows[:int(q.get('limit', 50))])
        if p == '/api/forecasts':
            t = int(q.get('trdr', 0))
            by_mtrl = {l['MTRL']: (s, l) for s in SUGS.values() if s['TRDR'] == t for l in s['LINES']}
            rows = []
            for m in TARGETS.get(t, []):
                s, l = by_mtrl.get(m, (None, None))
                rows.append({'TRDR': t, 'MTRL': m, 'ITEM_NAME': ITEMS[str(m)]['NAME'],
                             'PREDICTED_DEPLETION_DATE': l['PREDICTED_DEPLETION_DATE'] if l else None,
                             'CONFIDENCE': l['CONFIDENCE'] if l else None, 'urgency': s['urgency'] if s else 'low'})
            return self.send(200, rows)
        m = re.fullmatch(r'/api/customers/(\d+)/history', p)
        if m:
            t = int(m.group(1)); h = HISTORY.get(t)
            if h is None: return self.err(404, 'not_found', 'customer not found')
            mt = q.get('mtrl')
            return self.send(200, {'TRDR': t, 'items': [
                {'MTRL': k, 'ITEM_NAME': ITEMS[str(k)]['NAME'], 'points': [{'date': d, 'qty': v} for d, v in sorted(pts.items())]}
                for k, pts in sorted(h.items()) if not mt or str(k) == mt]})
        m = re.fullmatch(r'/api/suggestions/([\w-]+)/explanation', p)
        if m:
            s = SUGS.get(m.group(1))
            return self.send(200, mock_explanation(s)) if s else self.err(404, 'not_found', 'suggestion not found')
        if p == '/api/evaluation': return self.send(200, MOCK_EVALUATION)
        if p == '/api/calls': return self.send(200, list(CALLS.values())[::-1])
        if p == '/api/audit': return self.send(200, AUDIT[::-1])
        m = re.fullmatch(r'/api/suggestions/([\w-]+)', p)
        if m:
            s = SUGS.get(m.group(1))
            return self.send(200, s) if s else self.err(404, 'not_found', 'suggestion not found')
        self.err(404, 'not_found', 'unknown path')

    def do_POST(self):
        p = urlparse(self.path).path.rstrip('/'); actor = self.headers.get('X-Actor', 'unknown')
        try: b = self.body()
        except Exception: return self.err(400, 'bad_json', 'invalid JSON body')

        if p == '/api/admin/reset':
            with LOCK:
                SUGS.clear(); SUGS.update(_seed()); TOKENS.clear(); IDEMP.clear(); CALLS.clear()
            return self.send(200, {'ok': True, 'suggestions': len(SUGS)})

        if p == '/api/calls/events':
            sid = b.get('call_sid')
            if not sid: return self.err(400, 'bad_request', 'call_sid required')
            with LOCK:
                c = CALLS.setdefault(sid, {'call_sid': sid, 'salesman': b.get('salesman'), 'suggestion_ids': [], 'status': 'queued',
                                           'started_at': now(), 'ended_at': None, 'transcript': [], 'erp_draft_ids': []})
                if b.get('status'): c['status'] = b['status']
                if b.get('status') in ('ended', 'failed', 'cancelled'): c['ended_at'] = now()
                if b.get('text'): c['transcript'].append({'role': b.get('role', 'agent'), 'text': b['text'], 'at': now()})
                if b.get('suggestion_id') and b['suggestion_id'] not in c['suggestion_ids']: c['suggestion_ids'].append(b['suggestion_id'])
                if b.get('erp_draft_id'): c['erp_draft_ids'].append(b['erp_draft_id'])
            return self.send(200, {'ok': True})

        m = re.fullmatch(r'/api/suggestions/([\w-]+)/(lines/(\d+)/quantity|confirm|create-draft|cancel)', p)
        if not m: return self.err(404, 'not_found', 'unknown path')
        sid, action, mtrl = m.group(1), m.group(2), m.group(3)
        with LOCK:
            s = SUGS.get(sid)
            if not s: return self.err(404, 'not_found', 'suggestion not found')

            if mtrl:
                line = next((l for l in s['LINES'] if l['MTRL'] == int(mtrl)), None)
                if not line: return self.err(404, 'not_found', f'MTRL {mtrl} not in suggestion')
                if s['status'] in ('draft_created', 'posting', 'cancelled'): return self.err(409, 'locked', f"status is {s['status']}")
                if b.get('version') != s['version']: return self.err(409, 'version_conflict', f"current version is {s['version']}")
                qty = b.get('qty')
                if not isinstance(qty, int) or isinstance(qty, bool) or not (line['QTY_MIN'] <= qty <= line['QTY_MAX']):
                    return self.err(400, 'qty_out_of_bounds', f"qty must be integer in {line['QTY_MIN']}..{line['QTY_MAX']}")
                line['QTY1'] = qty; s['version'] += 1; s['status'] = 'modified'; s['updated_at'] = now()
                for t in [t for t, v in TOKENS.items() if v[0] == sid]: TOKENS.pop(t)   # παλιά confirmations άκυρα
                audit(actor, f'quantity {mtrl}={qty}', sid, 'ok'); return self.send(200, s)

            if action == 'confirm':
                if s['status'] not in ('proposed', 'modified', 'confirmed', 'failed'): return self.err(409, 'locked', f"status is {s['status']}")
                if b.get('version') != s['version']: return self.err(409, 'version_conflict', f"current version is {s['version']}")
                tok = secrets.token_urlsafe(16); TOKENS[tok] = (sid, s['version']); s['status'] = 'confirmed'
                audit(actor, 'confirm', sid, f"v{s['version']}")
                return self.send(200, {'confirmation_token': tok, 'snapshot': copy.deepcopy(s)})

            if action == 'cancel':
                if s['status'] in ('draft_created', 'posting'): return self.err(409, 'locked', f"status is {s['status']}")
                s['status'] = 'cancelled'; audit(actor, 'cancel', sid, 'ok'); return self.send(200, s)

            # create-draft
            key = b.get('idempotency_key')
            if not key: return self.err(400, 'bad_request', 'idempotency_key required')
            key = (sid, key)   # το ίδιο key σε άλλη πρόταση ΔΕΝ πρέπει να επιστρέφει το draft αυτής
            if key in IDEMP: return self.send(200, IDEMP[key])
            if s['status'] == 'draft_created':
                return self.send(200, {'erp_draft_id': s['erp_draft_id'], 'status': 'draft_created'})
            # Ένα αίτημα είναι ήδη στο ERP (π.χ. διπλό webhook/retry): ΚΑΝΕΝΑ δεύτερο POST.
            if s['status'] == 'posting':
                return self.err(409, 'in_progress', 'create-draft already in progress for this suggestion')
            t = TOKENS.get(b.get('confirmation_token'))
            if not t or t != (sid, s['version']): return self.err(409, 'not_confirmed', 'missing/stale confirmation_token')
            s['status'] = 'posting'
        code, resp = post_erp(erp_payload(s))   # έξω από το lock
        with LOCK:
            if code == 201:
                s['status'] = 'draft_created'; s['erp_draft_id'] = resp['id']; TOKENS.pop(b['confirmation_token'], None)
                out = {'erp_draft_id': resp['id'], 'status': 'draft_created'}; IDEMP[key] = out
                audit(actor, 'create-draft', sid, resp['id']); return self.send(200, out)
            s['status'] = 'failed'; audit(actor, 'create-draft', sid, f'ERP {code}')
            return self.err(502, 'erp_error', json.dumps(resp, ensure_ascii=False))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--port', type=int, default=8000)
    # Στο VPS (host networking, χωρίς firewall) τρέχει με --host 127.0.0.1 ώστε να μη βγαίνει στο internet.
    ap.add_argument('--host', default='0.0.0.0'); a = ap.parse_args()
    print(f'Mock App API on http://{a.host}:{a.port}  (fixture: {FIXTURE}, ERP: {ERP})')
    ThreadingHTTPServer((a.host, a.port), H).serve_forever()
