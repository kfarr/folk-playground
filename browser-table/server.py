#!/usr/bin/env python3
"""Serves the browser table and mediates between it and the Folk process.

GET  /            -> the table page
GET  /table.json  -> display size and card list, read from the app manifest
GET  /scene.json  -> whatever the app's draw wishes currently are
POST /cards       -> card positions, written as a Tcl list for Folk to read

    FOLK_TABLE=$PWD/folkville/browser-table.tcl python3 browser-table/server.py
"""
import http.server, json, os, shlex, socketserver, sys, threading

SCENE = "/tmp/browser-table-scene.json"
CARDS = "/tmp/browser-table-cards.json"
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", 4274))


def read_manifest(path):
    """Parse the same tiny DSL harness.folk sources: display / program / card."""
    table = {"display": [1200, 760], "cards": []}
    with open(path) as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            words = shlex.split(line)
            if words[0] == "display" and len(words) == 3:
                table["display"] = [int(words[1]), int(words[2])]
            elif words[0] == "card" and len(words) >= 6:
                table["cards"].append({
                    "kind": words[1],
                    "label": words[2],
                    "program": os.path.basename(words[3]),
                    "x": float(words[4]),
                    "y": float(words[5]),
                    "on": len(words) < 7 or words[6] != "off",
                })
    return table


manifest = os.environ.get("FOLK_TABLE")
if not manifest:
    sys.exit("server.py: set FOLK_TABLE to an app manifest, e.g.\n"
             "  FOLK_TABLE=$PWD/folkville/browser-table.tcl python3 browser-table/server.py")
TABLE = read_manifest(manifest)


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        body = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/table.json"):
            self._send(200, json.dumps(TABLE))
        elif self.path.startswith("/scene.json"):
            try:
                with open(SCENE) as f:
                    self._send(200, f.read())
            except Exception:
                self._send(200, '{"items":[]}')
        else:
            with open(os.path.join(HERE, "table.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        cards = json.loads(self.rfile.read(n) or "[]")
        # Tcl list of {kind cx cy angle}
        tcl = " ".join(
            "{%s %.3f %.3f %.3f}" % (c["kind"], c["x"], c["y"], c["angle"])
            for c in cards
        )
        # Unique temp name per thread: concurrent POSTs otherwise race on rename.
        tmp = "%s.%d.tmp" % (CARDS, threading.get_ident())
        with open(tmp, "w") as f:
            f.write(tcl)
        os.replace(tmp, CARDS)
        self._send(200, "{}")


socketserver.ThreadingTCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H) as httpd:
    print(f"browser table: http://localhost:{PORT}  ({os.path.basename(manifest)}, "
          f"{len(TABLE['cards'])} cards)")
    httpd.serve_forever()
