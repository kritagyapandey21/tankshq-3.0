"""Local dev server for the frontend with clean URLs, matching production (Nginx / Vercel).

    python dev_server.py [port]        (default 3000)

/login serves login.html, and /login.html redirects to /login. Everything else is served as-is.
"""

import http.server
import os
import sys
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.abspath(__file__))


class CleanUrlHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def _route(self):
        """Redirect *.html to the clean URL, or map a clean URL to its .html file. Returns True if it redirected."""
        parts = urlsplit(self.path)
        path, query = parts.path, ("?" + parts.query) if parts.query else ""
        if path.endswith(".html"):
            target = "/" if path == "/index.html" else path[:-5]
            self.send_response(301)
            self.send_header("Location", target + query)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        last = path.rsplit("/", 1)[-1]
        if path != "/" and "." not in last and os.path.isfile(os.path.join(ROOT, path.lstrip("/") + ".html")):
            self.path = path + ".html" + query
        return False

    def do_GET(self):
        if not self._route():
            super().do_GET()

    def do_HEAD(self):
        if not self._route():
            super().do_HEAD()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    with http.server.ThreadingHTTPServer(("", port), CleanUrlHandler) as server:
        print(f"Serving the frontend with clean URLs on http://localhost:{port}")
        server.serve_forever()
