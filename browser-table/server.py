#!/usr/bin/env python3
"""Serves the browser table and mediates between it and the Folk process.

GET  /            -> the mouse table page
GET  /phone       -> the phone table page (camera + overlay; see README)
GET  /tags        -> printable AprilTag cards + calibration corners
GET  /vendor/*    -> the vendored tag-detection library
GET  /table.json  -> display size and card list, read from the app manifest
GET  /scene.json  -> whatever the app's draw wishes currently are
POST /cards       -> card positions, written as a Tcl list for Folk to read

Serves plain HTTP on PORT (default 4274) and, when openssl is available, the
same thing over HTTPS on PORT+1 with a self-signed certificate — iOS refuses
camera access to plain-HTTP origins, so the phone uses the https:// address
(accept the certificate warning once).

    FOLK_TABLE=$PWD/folkville/browser-table.tcl python3 browser-table/server.py
"""
import http.server, json, os, shlex, socket, socketserver, ssl, subprocess, sys, threading

SCENE = "/tmp/browser-table-scene.json"
CARDS = "/tmp/browser-table-cards.json"
CERTDIR = "/tmp/browser-table-cert"
HERE = os.path.dirname(os.path.abspath(__file__))
HOST = os.environ.get("HOST", "0.0.0.0")   # the phone connects over the LAN
PORT = int(os.environ.get("PORT", 4274))

PAGES = {"/": "table.html", "/phone": "phone.html", "/tags": "tags.html"}


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
        path = self.path.split("?", 1)[0]
        if path == "/table.json":
            self._send(200, json.dumps(TABLE))
        elif path == "/scene.json":
            try:
                with open(SCENE) as f:
                    self._send(200, f.read())
            except Exception:
                self._send(200, '{"items":[]}')
        elif path.startswith("/vendor/"):
            fp = os.path.join(HERE, "vendor", os.path.basename(path))
            if os.path.isfile(fp):
                with open(fp, "rb") as f:
                    self._send(200, f.read(), "text/javascript; charset=utf-8")
            else:
                self._send(404, "{}")
        elif path == "/test.png" and os.environ.get("BROWSER_TABLE_TEST_IMG"):
            # test hook: lets the test suite feed phone.html?img=/test.png a
            # synthetic table photo from the same origin
            with open(os.environ["BROWSER_TABLE_TEST_IMG"], "rb") as f:
                self._send(200, f.read(), "image/png")
        elif path in PAGES:
            with open(os.path.join(HERE, PAGES[path]), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        else:
            self._send(404, "{}")

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


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))          # no traffic sent; picks the LAN interface
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def tls_context():
    """A long-lived self-signed cert in /tmp — good enough for a LAN toy; the
    phone accepts it once. For a warning-free setup use mkcert instead."""
    cert, key = os.path.join(CERTDIR, "cert.pem"), os.path.join(CERTDIR, "key.pem")
    if not (os.path.isfile(cert) and os.path.isfile(key)):
        os.makedirs(CERTDIR, exist_ok=True)
        r = subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", key, "-out", cert, "-days", "3650",
             "-subj", "/CN=folk-browser-table"],
            capture_output=True)
        if r.returncode != 0:
            return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    return ctx


socketserver.ThreadingTCPServer.allow_reuse_address = True
ip = lan_ip()
try:
    ctx = tls_context()
except Exception:
    ctx = None
print(f"browser table: http://localhost:{PORT}  ({os.path.basename(manifest)}, "
      f"{len(TABLE['cards'])} cards)")
if ctx:
    https = socketserver.ThreadingTCPServer((HOST, PORT + 1), H)
    https.socket = ctx.wrap_socket(https.socket, server_side=True)
    threading.Thread(target=https.serve_forever, daemon=True).start()
    print(f"phone table:   https://{ip}:{PORT + 1}/phone  (accept the certificate once)")
    print(f"print tags:    http://localhost:{PORT}/tags")
else:
    print("phone table:   (no openssl found — iOS needs HTTPS for the camera; "
          "install openssl or serve via mkcert)")
with socketserver.ThreadingTCPServer((HOST, PORT), H) as httpd:
    httpd.serve_forever()
