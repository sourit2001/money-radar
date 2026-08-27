"""Local HTTP server for the Reddit opportunity radar."""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import parse

from .config import PUBLIC_DIR
from .opportunities import build_opportunities
from .storage import connect, list_posts, metadata


def json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def static_response(handler: BaseHTTPRequestHandler, static_dir: Path, path: str) -> None:
    relative = "index.html" if path == "/" else path.lstrip("/")
    file_path = (static_dir / relative).resolve()
    if not str(file_path).startswith(str(static_dir.resolve())) or not file_path.is_file():
        handler.send_error(404)
        return
    content = file_path.read_bytes()
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


def make_handler(db_path: str | Path, static_dir: str | Path = PUBLIC_DIR) -> type[BaseHTTPRequestHandler]:
    db_path = Path(db_path)
    static_dir = Path(static_dir)

    class RadarHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            parsed = parse.urlparse(self.path)
            if parsed.path == "/api/posts":
                params = parse.parse_qs(parsed.query)
                conn = connect(db_path)
                posts = list_posts(
                    conn,
                    channel=params.get("channel", [None])[0] or None,
                    subreddit=params.get("subreddit", [None])[0] or None,
                    min_value_score=int(params.get("min_score", ["1"])[0] or 1),
                    search=params.get("search", [None])[0] or None,
                )
                json_response(self, {"posts": posts, "meta": metadata(conn)})
                return
            if parsed.path == "/api/opportunities":
                params = parse.parse_qs(parsed.query)
                conn = connect(db_path)
                posts = list_posts(
                    conn,
                    channel=params.get("channel", [None])[0] or None,
                    subreddit=params.get("subreddit", [None])[0] or None,
                    min_value_score=int(params.get("min_score", ["1"])[0] or 1),
                    search=params.get("search", [None])[0] or None,
                )
                json_response(self, {"opportunities": build_opportunities(posts), "meta": metadata(conn)})
                return
            if parsed.path == "/api/health":
                json_response(self, {"ok": True})
                return
            static_response(self, static_dir, parsed.path)

    return RadarHandler


def serve(db_path: str | Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    class ReuseThreadingHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = True

    server = ReuseThreadingHTTPServer((host, port), make_handler(db_path))
    print(f"Money Radar running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Money Radar.")
    finally:
        server.server_close()
