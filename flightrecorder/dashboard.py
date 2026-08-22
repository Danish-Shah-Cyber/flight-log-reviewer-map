from __future__ import annotations

import cgi
import html
import os
import tempfile
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .analysis import analyze
from .binlog import read_bin
from .insights import generate_insights
from .report import write_html_report
from .tlog import read_tlog


DEFAULT_MAX_UPLOAD_MB = 200


def _max_upload_bytes() -> int:
    try:
        megabytes = int(os.environ.get("MAX_UPLOAD_MB", str(DEFAULT_MAX_UPLOAD_MB)))
    except ValueError:
        megabytes = DEFAULT_MAX_UPLOAD_MB
    return max(1, min(megabytes, 200)) * 1024 * 1024


MAX_UPLOAD_BYTES = _max_upload_bytes()
MAX_UPLOAD_MB = MAX_UPLOAD_BYTES // (1024 * 1024)
# Multipart form framing is additional to the file itself.
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024


def _temp_root() -> Path:
    root = Path(os.environ.get("FLIGHTRECORDER_TMP_DIR", "work/tmp"))
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


PAGE = """<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>Flight Data Dashboard</title><style>
:root{color-scheme:light;--bg:#f5f7fb;--panel:#fff;--panel-2:#eef2f7;--text:#18202b;--muted:#657184;--line:#d9e0ea;--accent:#1769c2;--danger:#bf3145;--shadow:0 12px 36px rgba(29,39,58,.11)}
[data-theme=dark]{color-scheme:dark;--bg:#0e131b;--panel:#151d29;--panel-2:#101722;--text:#edf3fb;--muted:#98a7ba;--line:#263447;--accent:#65a9ff;--danger:#ff6678;--shadow:0 16px 40px rgba(0,0,0,.28)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 Inter,Segoe UI,Arial,sans-serif}
.shell{min-height:100vh;display:grid;place-items:center;padding:28px}.panel{width:min(760px,100%);background:var(--panel);border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow);padding:26px}
.top{display:flex;justify-content:space-between;gap:18px;align-items:start;margin-bottom:22px}h1{font-family:D-DIN-Bold,"D DIN","Arial Narrow",Arial,sans-serif;letter-spacing:0;font-size:34px;line-height:1.05;margin:0 0 8px}.muted{color:var(--muted)}
.toggle{border:1px solid var(--line);background:var(--panel-2);color:var(--text);border-radius:8px;padding:9px 11px;cursor:pointer;white-space:nowrap}
.drop{display:grid;gap:10px;border:1px dashed var(--line);border-radius:8px;padding:34px 20px;text-align:center;cursor:pointer;background:var(--panel-2);margin-bottom:14px}.drop:hover{border-color:var(--accent)}
input[type=file]{max-width:100%;margin:auto}button.primary{width:100%;background:var(--accent);color:#fff;border:0;border-radius:8px;padding:12px 16px;font-weight:750;font-size:15px;cursor:pointer}
.facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:18px}.fact{background:var(--panel-2);border:1px solid var(--line);border-radius:8px;padding:12px}.fact strong{display:block;margin-bottom:3px}
.note{font-size:14px;margin-top:18px}.error{background:color-mix(in srgb,var(--danger) 14%,var(--panel));border:1px solid var(--danger);padding:14px;border-radius:8px;margin-bottom:16px}
@media(max-width:720px){.top{display:block}.toggle{margin-top:12px}.facts{grid-template-columns:1fr}}
</style></head><body><main class="shell"><section class="panel">{error}<div class="top"><div><h1>Flight Data Dashboard</h1><p class="muted">Upload Mission Planner telemetry or an ArduPilot onboard log.</p></div><button class="toggle" id="themeToggle" type="button">Toggle theme</button></div>
<form method="post" enctype="multipart/form-data" action="/analyze">
<label class="drop"><strong>Choose a .tlog, .BIN, or .log file</strong><span class="muted">The generated dashboard opens after analysis.</span>
<input required type="file" name="flight_log" accept=".tlog,.bin,.log"></label><button class="primary" type="submit">Analyze flight</button></form>
<div class="facts"><div class="fact"><strong>Local processing</strong><span class="muted">Uploads are deleted after processing.</span></div><div class="fact"><strong>{max_upload_mb} MB limit</strong><span class="muted">Configurable with MAX_UPLOAD_MB.</span></div><div class="fact"><strong>Evidence first</strong><span class="muted">Reports label missing or weak data.</span></div></div>
<p class="muted note">Engineering aid only; not a certified safety determination.</p></section></main><script>
const themeKey="flight-dashboard-theme";document.documentElement.dataset.theme=localStorage.getItem(themeKey)||"light";
document.getElementById("themeToggle").addEventListener("click",()=>{const next=document.documentElement.dataset.theme==="dark"?"light":"dark";document.documentElement.dataset.theme=next;localStorage.setItem(themeKey,next);});
</script></body></html>"""


def _page(error: str = "") -> bytes:
    return PAGE.replace("{max_upload_mb}", str(MAX_UPLOAD_MB)).replace("{error}", error).encode()


def _read_flight_log(upload: Path, suffix: str, temp_dir: str):
    if suffix == ".tlog":
        return read_tlog(upload)
    return read_bin(upload)


class DashboardHandler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, content_type: str = "text/html; charset=utf-8", status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        if path == "/":
            self._send(_page())
            return
        self._send(b"Not found", "text/plain", 404)

    def do_POST(self):
        if self.path != "/analyze":
            self._send(b"Not found", "text/plain", 404)
            return
        try:
            tempfile.tempdir = str(_temp_root())
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise ValueError(f"The upload is empty or exceeds {MAX_UPLOAD_MB} MB")
            form = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", "")},
            )
            if "flight_log" not in form:
                raise ValueError("No flight log was uploaded")
            item = form["flight_log"]
            if isinstance(item, list) or not getattr(item, "file", None):
                raise ValueError("Please upload one flight log")
            original = Path(item.filename or "").name
            suffix = Path(original).suffix.lower()
            if suffix not in {".tlog", ".bin", ".log"}:
                raise ValueError("Please select a .tlog, .BIN, or .log file")
            with tempfile.TemporaryDirectory(prefix="flight-analyzer-", dir=_temp_root()) as temp_dir:
                token = uuid.uuid4().hex[:10]
                upload = Path(temp_dir) / f"{token}{suffix}"
                uploaded_bytes = 0
                with upload.open("wb") as destination:
                    while block := item.file.read(1024 * 1024):
                        uploaded_bytes += len(block)
                        if uploaded_bytes > MAX_UPLOAD_BYTES:
                            raise ValueError(f"The upload exceeds {MAX_UPLOAD_MB} MB")
                        destination.write(block)
                if uploaded_bytes == 0:
                    raise ValueError("The uploaded file is empty")

                samples = _read_flight_log(upload, suffix, temp_dir)
                report = Path(temp_dir) / f"flight_report_{token}.html"
                write_html_report(report, samples, analyze(samples), generate_insights(samples))
                report_bytes = report.read_bytes()

            self._send(report_bytes)
        except Exception as error:
            message = f'<div class="error"><strong>Analysis failed:</strong> {html.escape(str(error))}</div>'
            self._send(_page(message), status=400)

    def log_message(self, format, *args):
        print(f"Dashboard: {format % args}")


def run_dashboard(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    url = f"http://{host}:{port}"
    print(f"Flight Log Analyzer running at {url}")
    print("Press Ctrl+C to stop it.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
