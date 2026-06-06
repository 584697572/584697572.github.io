from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json
import re
import sys


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "personal_log"
DATE_PATTERN = re.compile(r"^\d{8}$")


class BlogHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/personal-log":
            self.handle_get_log(parsed)
            return

        if parsed.path == "/api/search-paths":
            self.handle_search_paths()
            return

        super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/personal-log":
            self.handle_post_log(parsed)
            return

        self.send_error(404)

    def handle_get_log(self, parsed):
        date = self.get_date(parsed)
        if not date:
            self.send_json({"error": "invalid date"}, status=400)
            return

        file_path = LOG_DIR / f"{date}.md"
        content = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
        self.send_json({
            "date": date,
            "path": f"personal_log/{date}.md",
            "content": content,
        })

    def handle_post_log(self, parsed):
        date = self.get_date(parsed)
        if not date:
            self.send_json({"error": "invalid date"}, status=400)
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)

        try:
            data = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self.send_json({"error": "invalid json"}, status=400)
            return

        content = data.get("content", "")
        if not isinstance(content, str):
            self.send_json({"error": "content must be a string"}, status=400)
            return

        LOG_DIR.mkdir(exist_ok=True)
        file_path = LOG_DIR / f"{date}.md"
        file_path.write_text(content, encoding="utf-8")
        self.send_json({
            "ok": True,
            "date": date,
            "path": f"personal_log/{date}.md",
        })

    def handle_search_paths(self):
        paths = []

        for path in ROOT.rglob("*.md"):
            if ".git" in path.parts:
                continue

            paths.append(path.relative_to(ROOT).as_posix())

        self.send_json({"paths": sorted(paths)})

    def get_date(self, parsed):
        query = parse_qs(parsed.query)
        date = query.get("date", [""])[0]

        if not DATE_PATTERN.match(date):
            return None

        return date

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
    server = ThreadingHTTPServer(("127.0.0.1", port), BlogHandler)
    print(f"Serving {ROOT} at http://127.0.0.1:{port}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
