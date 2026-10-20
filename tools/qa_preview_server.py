"""Key-free preview server for product QA; no application APIs or profile data."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        decoded = unquote(urlsplit(path).path).lstrip("/")
        parts = Path(decoded).parts
        if any(part.startswith(".") or part in ("server", "node_modules", "profiles", "runtime_data", "BrowserData") for part in parts):
            return str(ROOT / "__qa_not_found__")
        allowed = decoded.startswith("web_support/") or decoded.startswith("docs/reports/product-qa/")
        if not allowed:
            return str(ROOT / "__qa_not_found__")
        candidate = (ROOT / decoded).resolve()
        if not candidate.is_relative_to(ROOT):
            return str(ROOT / "__qa_not_found__")
        return str(candidate)

    def list_directory(self, path):
        self.send_error(403, "Directory listing disabled")
        return None

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print(f"QA_PREVIEW http://127.0.0.1:{server.server_port} PID {os.getpid()}", flush=True)
    server.serve_forever()
