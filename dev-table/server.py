#!/usr/bin/env python3
"""Bridge between the browser and the real Folk process.

GET  /            -> the table page
GET  /scene.json  -> whatever folkville's draw wishes currently are
POST /tools       -> card positions, written as a Tcl list Folk reads
"""
import http.server, json, os, socketserver, threading

SCENE = "/tmp/folkville-scene.json"
TOOLS = "/tmp/folkville-tools.json"
HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 4274


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
        if self.path.startswith("/scene.json"):
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
        tmp = "%s.%d.tmp" % (TOOLS, threading.get_ident())
        with open(tmp, "w") as f:
            f.write(tcl)
        os.replace(tmp, TOOLS)
        self._send(200, "{}")


socketserver.ThreadingTCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H) as httpd:
    print(f"folkville table: http://localhost:{PORT}")
    httpd.serve_forever()
