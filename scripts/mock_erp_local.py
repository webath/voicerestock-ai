#!/usr/bin/env python3
"""Τρέχει το επίσημο team_pack/mock_erp_server.py ΧΩΡΙΣ να το αλλάξει, αλλά μόνο στο 127.0.0.1.

Το αρχικό ακούει σε 0.0.0.0: όποιος είναι στο ίδιο Wi-Fi μπορεί να διαβάσει τα τιμολόγια και να γράψει draft
παραγγελίες. Εδώ το ίδιο ακριβώς πρόγραμμα δένει μόνο στον ίδιο τον υπολογιστή.

    python3 scripts/mock_erp_local.py --port 8080
"""
import http.server
import runpy
from pathlib import Path


class LocalOnly(http.server.ThreadingHTTPServer):
    def __init__(self, address, handler):
        super().__init__(("127.0.0.1", address[1]), handler)


http.server.ThreadingHTTPServer = LocalOnly      # το mock κάνει «from http.server import ThreadingHTTPServer» όταν ξεκινά
runpy.run_path(str(Path(__file__).resolve().parent.parent / "team_pack" / "mock_erp_server.py"), run_name="__main__")
