"""Local dev server without the Vercel CLI: serves public/ and routes /api/analyze to api/analyze.py, /api/vault to
api/vault.py (Phase 1 Vault Risk Analyzer) and /api/countermove to api/countermove.py (Phase 2, read-only).

    python scripts/dev_server.py [port]        -> http://localhost:8000/, /xray.html, /vault.html and /countermove.html
"""
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

from analyze import handler as AnalyzeHandler  # noqa: E402
from countermove import handler as CountermoveHandler  # noqa: E402
from vault import handler as VaultHandler  # noqa: E402


class Dev(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT / "public"), **k)

    def do_GET(self):
        if self.path.startswith("/api/analyze"):
            return AnalyzeHandler.do_GET(self)
        if self.path.startswith("/api/vault"):
            return VaultHandler.do_GET(self)
        if self.path.startswith("/api/countermove"):
            return CountermoveHandler.do_GET(self)
        return super().do_GET()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"FAULTLINE dev server on http://localhost:{port}/")
    ThreadingHTTPServer(("127.0.0.1", port), Dev).serve_forever()
