from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json
import re
import sys


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "personal_log"
LOG_MANIFEST_FILE = LOG_DIR / "index.json"
PAPER_DIR = ROOT / "paper_files"
PAPER_MANIFEST_FILE = PAPER_DIR / "index.json"
DATE_PATTERN = re.compile(r"^\d{8}$")
UNSAFE_FILENAME = re.compile(r"[<>:\"/\\|?*\x00-\x1f]")


class BlogHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/personal-log":
            self.handle_get_log(parsed)
            return

        if parsed.path == "/api/personal-log-list":
            self.handle_log_list()
            return

        if parsed.path == "/api/paper-list":
            self.handle_paper_list()
            return

        if parsed.path == "/api/markdown-file":
            self.handle_get_markdown_file(parsed)
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

        if parsed.path == "/api/paper-upload":
            self.handle_paper_upload()
            return

        if parsed.path == "/api/markdown-file":
            self.handle_post_markdown_file()
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

        data = self.read_json_body()
        if data is None:
            return

        content = data.get("content", "")
        if not isinstance(content, str):
            self.send_json({"error": "content must be a string"}, status=400)
            return

        content = self.format_log_content(content)
        LOG_DIR.mkdir(exist_ok=True)
        file_path = LOG_DIR / f"{date}.md"
        file_path.write_text(content, encoding="utf-8")
        self.write_json_file(LOG_MANIFEST_FILE, {"logs": self.collect_logs()})
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

    def handle_log_list(self):
        logs = self.collect_logs()
        self.write_json_file(LOG_MANIFEST_FILE, {"logs": logs})
        self.send_json({"logs": logs})

    def handle_paper_list(self):
        papers = self.collect_papers()
        self.write_json_file(PAPER_MANIFEST_FILE, {"papers": papers})
        self.send_json({"papers": papers})

    def handle_paper_upload(self):
        data = self.read_json_body()
        if data is None:
            return

        filename = data.get("filename", "")
        content = data.get("content", "")
        if not isinstance(filename, str) or not isinstance(content, str):
            self.send_json({"error": "filename and content must be strings"}, status=400)
            return

        PAPER_DIR.mkdir(exist_ok=True)
        file_path = self.unique_paper_path(filename)
        file_path.write_text(content, encoding="utf-8")

        papers = self.collect_papers()
        self.write_json_file(PAPER_MANIFEST_FILE, {"papers": papers})
        rel_path = file_path.relative_to(ROOT).as_posix()
        paper = next((item for item in papers if item["path"] == rel_path), None)
        self.send_json({"ok": True, "paper": paper})

    def handle_get_markdown_file(self, parsed):
        query = parse_qs(parsed.query)
        rel_path = query.get("path", [""])[0]
        file_path = self.resolve_editable_markdown(rel_path)
        if not file_path or not file_path.exists():
            self.send_json({"error": "file not found"}, status=404)
            return

        self.send_json({
            "path": file_path.relative_to(ROOT).as_posix(),
            "content": file_path.read_text(encoding="utf-8"),
        })

    def handle_post_markdown_file(self):
        data = self.read_json_body()
        if data is None:
            return

        rel_path = data.get("path", "")
        content = data.get("content", "")
        if not isinstance(rel_path, str) or not isinstance(content, str):
            self.send_json({"error": "path and content must be strings"}, status=400)
            return

        file_path = self.resolve_editable_markdown(rel_path)
        if not file_path:
            self.send_json({"error": "invalid path"}, status=400)
            return

        if self.is_relative_to(file_path, LOG_DIR):
            content = self.format_log_content(content)

        file_path.parent.mkdir(exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        if self.is_relative_to(file_path, PAPER_DIR):
            self.write_json_file(PAPER_MANIFEST_FILE, {"papers": self.collect_papers()})
        if self.is_relative_to(file_path, LOG_DIR):
            self.write_json_file(LOG_MANIFEST_FILE, {"logs": self.collect_logs()})

        self.send_json({"ok": True, "path": file_path.relative_to(ROOT).as_posix()})

    def collect_logs(self):
        logs = []

        if LOG_DIR.exists():
            for path in LOG_DIR.glob("*.md"):
                date = path.stem
                if not DATE_PATTERN.match(date):
                    continue

                logs.append({
                    "date": date,
                    "path": path.relative_to(ROOT).as_posix(),
                    "updated": path.stat().st_mtime,
                })

        return sorted(logs, key=lambda item: item["date"], reverse=True)

    def collect_papers(self):
        manifest = self.read_json_file(PAPER_MANIFEST_FILE, {"papers": []})
        previous = {
            item.get("path"): item
            for item in manifest.get("papers", [])
            if isinstance(item, dict)
        }
        papers = []

        if PAPER_DIR.exists():
            for path in PAPER_DIR.glob("*.md"):
                rel_path = path.relative_to(ROOT).as_posix()
                stat = path.stat()
                old_item = previous.get(rel_path, {})
                uploaded = old_item.get("uploaded", stat.st_ctime)

                papers.append({
                    "name": path.name,
                    "title": self.title_from_markdown(path),
                    "path": rel_path,
                    "uploaded": uploaded,
                    "updated": stat.st_mtime,
                })

        return sorted(papers, key=lambda item: (item["uploaded"], item["updated"]), reverse=True)

    def title_from_markdown(self, path):
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("# "):
                    return line[2:].strip() or path.stem
        except UnicodeDecodeError:
            pass

        return path.stem

    def unique_paper_path(self, filename):
        safe_name = self.safe_markdown_filename(filename)
        candidate = PAPER_DIR / safe_name
        stem = candidate.stem
        suffix = candidate.suffix
        counter = 2

        while candidate.exists():
            candidate = PAPER_DIR / f"{stem}-{counter}{suffix}"
            counter += 1

        return candidate

    def safe_markdown_filename(self, filename):
        name = Path(filename).name.strip()
        name = UNSAFE_FILENAME.sub("_", name)
        name = re.sub(r"\s+", "_", name)

        if not name or name.lower() == ".md":
            name = "paper.md"
        if not name.lower().endswith(".md"):
            name += ".md"

        return name

    def resolve_editable_markdown(self, rel_path):
        if not rel_path or "\x00" in rel_path:
            return None

        target = (ROOT / rel_path).resolve()
        if target.suffix.lower() != ".md":
            return None
        if self.is_relative_to(target, PAPER_DIR) or self.is_relative_to(target, LOG_DIR):
            return target

        return None

    def is_relative_to(self, path, parent):
        try:
            path.resolve().relative_to(parent.resolve())
            return True
        except ValueError:
            return False

    def format_log_content(self, content):
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        lines = []

        for line in normalized.split("\n"):
            clean = re.sub(r"[ \t]+$", "", line)
            lines.append(clean + "  " if clean else "")

        return "\n".join(lines)
    def get_date(self, parsed):
        query = parse_qs(parsed.query)
        date = query.get("date", [""])[0]

        if not DATE_PATTERN.match(date):
            return None

        return date

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)

        try:
            return json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self.send_json({"error": "invalid json"}, status=400)
            return None

    def read_json_file(self, path, default):
        if not path.exists():
            return default

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return default

    def write_json_file(self, path, data):
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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