#!/usr/bin/env python3
"""A logging HTTP proxy, so a claim about what the client sends is measured.

The crate's transaction actions are `pub(crate)`, so a caller cannot ask what
updates an action will emit. Reading the source answers it; putting a proxy in
front of the catalog answers it from the wire, which is the answer a reader can
check without installing the crate.

Used by run_writes.py against the local control catalog only. It logs the
method, the path, the query string and, for a request with a JSON body, the
`updates` and `requirements` kinds inside it. Header VALUES are never logged:
one of them is a bearer token.
"""

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


def summarise(body):
    """The shape of a JSON body: update kinds, requirement kinds, key names.

    Values are deliberately absent. A property value is the caller's, a
    location is a path on someone's storage, and neither is needed to say
    which request went out.
    """
    if not body:
        return None
    try:
        doc = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"body": "not json", "bytes": len(body)}
    if not isinstance(doc, dict):
        return {"body": type(doc).__name__, "bytes": len(body)}
    out = {"keys": sorted(doc)}
    updates = doc.get("updates")
    if isinstance(updates, list):
        out["updates"] = [u.get("action") for u in updates
                          if isinstance(u, dict)]
    reqs = doc.get("requirements")
    if isinstance(reqs, list):
        out["requirements"] = [r.get("type") for r in reqs
                               if isinstance(r, dict)]
    return out


class Proxy(BaseHTTPRequestHandler):
    upstream = None
    log = None
    lock = threading.Lock()
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass                                          # the record is self.log

    def _relay(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        url = self.upstream + self.path
        req = urllib.request.Request(url, data=body or None, method=method)
        for k, v in self.headers.items():
            if k.lower() not in HOP_BY_HOP and k.lower() != "host":
                req.add_header(k, v)
        try:
            with urllib.request.urlopen(req) as resp:
                status, payload = resp.status, resp.read()
                headers = [(k, v) for k, v in resp.getheaders()
                           if k.lower() not in HOP_BY_HOP]
        except urllib.error.HTTPError as e:
            status, payload = e.code, e.read()
            headers = [(k, v) for k, v in e.headers.items()
                       if k.lower() not in HOP_BY_HOP]
        except urllib.error.URLError as e:
            status, payload, headers = 599, str(e.reason).encode(), []

        path, _, query = self.path.partition("?")
        with self.lock:
            self.log.append({
                "method": method,
                "path": path,
                "query": query,
                "status": status,
                "sent": summarise(body),
            })

        self.send_response(status)
        for k, v in headers:
            if k.lower() != "content-length":
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self._relay("GET")

    def do_POST(self):
        self._relay("POST")

    def do_HEAD(self):
        self._relay("HEAD")

    def do_PUT(self):
        self._relay("PUT")

    def do_DELETE(self):
        self._relay("DELETE")


def start(upstream, host="127.0.0.1", port=0):
    """Run the proxy on a thread. Returns (base_url, log_list, shutdown)."""
    log = []
    handler = type("BoundProxy", (Proxy,), {"upstream": upstream, "log": log})
    server = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://%s:%d" % (host, server.server_address[1])

    def shutdown():
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    return base, log, shutdown
