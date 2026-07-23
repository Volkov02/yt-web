import sys
import os
import json
import queue
import threading
import webbrowser
import re
from pathlib import Path

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import yt_dlp

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def get_ffmpeg_exe() -> tuple[str | None, str]:
    """Return (full_path_to_ffmpeg_exe_or_None, debug_message).

    Returns the FULL PATH to the executable so yt-dlp doesn't need to
    guess the filename (imageio_ffmpeg names it ffmpeg.win64.vX.Y.Z.exe).
    """
    import shutil

    # 1. Next to running script / exe — look for any ffmpeg*.exe
    if getattr(sys, "frozen", False):
        candidates = [Path(sys.executable).parent]
    else:
        candidates = [
            Path(__file__).resolve().parent,
            Path(__file__).resolve().parent.parent,
        ]

    checked = []
    for d in candidates:
        # Exact name first
        for name in ("ffmpeg.exe", "ffmpeg"):
            p = d / name
            checked.append(str(p))
            if p.exists():
                return str(p), f"[ffmpeg] found: {p}"
        # Any ffmpeg*.exe in the folder
        for p in d.glob("ffmpeg*.exe"):
            return str(p), f"[ffmpeg] found (glob): {p}"

    # 2. imageio_ffmpeg — returns versioned exe like ffmpeg.win64.v7.0.2.exe
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        print(f"[startup] imageio_ffmpeg.get_ffmpeg_exe() = {exe!r}", flush=True)
        if exe and Path(exe).exists():
            return str(exe), f"[ffmpeg] imageio_ffmpeg: {exe}"
        else:
            checked.append(f"imageio_ffmpeg returned {exe!r} — not on disk")
    except Exception as e:
        checked.append(f"imageio_ffmpeg exception: {e}")
        print(f"[startup] imageio_ffmpeg error: {e}", flush=True)

    # 3. System PATH
    found = shutil.which("ffmpeg")
    if found:
        return found, f"[ffmpeg] system PATH: {found}"

    msg = "[ffmpeg] NOT FOUND\nChecked:\n" + "\n".join(f"  {c}" for c in checked)
    print(msg, flush=True)
    return None, msg


def detect_js_runtime() -> tuple[str | None, str]:
    """Return (yt-dlp js_runtimes value or None, debug_message).
    Format expected by yt-dlp: 'name:/full/path' e.g. 'node:C:\\...\\node.exe'
    """
    import shutil
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    for name in ("deno", "node", "bun"):
        local = base / f"{name}.exe"
        if local.exists():
            val = f"{name}:{local}"
            return val, f"[js] found {name} at {local}"
        found = shutil.which(name)
        if found:
            val = f"{name}:{found}"
            return val, f"[js] found {name} in PATH: {found}"
    return None, "[js] no runtime found — using android player fallback"


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__, template_folder=resource_path("templates"))

# ---------------------------------------------------------------------------
# Download state
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_state: dict = {
    "running": False,
    "queue": queue.Queue(),
    "stop": threading.Event(),
}

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mK]")


def _clean(s: str) -> str:
    return ANSI_RE.sub("", s or "").strip()


# ---------------------------------------------------------------------------
# yt-dlp hooks & logger
# ---------------------------------------------------------------------------

class _Logger:
    def __init__(self, q: queue.Queue):
        self._q = q

    def debug(self, msg: str):
        msg = _clean(msg)
        if msg.startswith("[debug]"):
            return
        self._q.put({"t": "log", "msg": msg})

    def info(self, msg: str):
        self._q.put({"t": "log", "msg": _clean(msg)})

    def warning(self, msg: str):
        self._q.put({"t": "log", "msg": "⚠ " + _clean(msg)})

    def error(self, msg: str):
        self._q.put({"t": "log", "msg": "✖ " + _clean(msg)})


class _StopSignal(Exception):
    pass


def _make_progress_hook(q: queue.Queue, stop: threading.Event):
    def hook(d: dict):
        if stop.is_set():
            raise _StopSignal()

        status = d.get("status")
        if status == "downloading":
            try:
                pct = float(_clean(d.get("_percent_str", "0%")).replace("%", ""))
            except ValueError:
                pct = 0.0
            total = _clean(d.get("_total_bytes_str") or d.get("_total_bytes_estimate_str") or "?")
            speed = _clean(d.get("_speed_str") or "?")
            eta   = _clean(d.get("_eta_str") or "?")
            q.put({"t": "progress", "pct": pct, "total": total, "speed": speed, "eta": eta})
        elif status == "finished":
            q.put({"t": "status", "msg": "Processing…"})

    return hook


def _make_pp_hook(q: queue.Queue):
    def hook(d: dict):
        if d.get("status") == "started":
            pp = d.get("postprocessor", "")
            if "Merger" in pp:
                q.put({"t": "status", "msg": "Merging video + audio…"})
            elif "FFmpegExtractAudio" in pp:
                q.put({"t": "status", "msg": "Converting to MP3…"})
    return hook


# ---------------------------------------------------------------------------
# Format selector
# ---------------------------------------------------------------------------

_FORMATS = {
    "best":  "bestvideo+bestaudio/best",
    "2160":  "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
    "1080":  "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720":   "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480":   "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "audio": "bestaudio/best",
}


def _build_opts(out_dir: str, quality: str, q: queue.Queue, stop: threading.Event,
                cookies_browser: str = "") -> dict:
    opts: dict = {
        "outtmpl":             str(Path(out_dir) / "%(title).180B [%(id)s].%(ext)s"),
        "no_playlist":         True,
        "logger":              _Logger(q),
        "progress_hooks":      [_make_progress_hook(q, stop)],
        "postprocessor_hooks": [_make_pp_hook(q)],
        "format":              _FORMATS.get(quality, _FORMATS["best"]),
    }

    # Cookies from the user's browser. Without them YouTube gates the
    # high-res DASH formats behind a PO token and yt-dlp falls back to
    # the progressive 360p format 18 — so HD selections silently degrade.
    if cookies_browser:
        opts["cookiesfrombrowser"] = (cookies_browser,)
        q.put({"t": "log", "msg": f"[cookies] using {cookies_browser} profile"})
    else:
        q.put({"t": "log", "msg": "⚠ no cookies — YouTube may limit quality to 360p"})

    # ffmpeg — pass full exe path so yt-dlp doesn't need to guess filename
    ffmpeg_exe, ffmpeg_msg = get_ffmpeg_exe()
    q.put({"t": "log", "msg": ffmpeg_msg})
    if ffmpeg_exe is None:
        q.put({"t": "log", "msg": "⚠ ffmpeg missing — put ffmpeg.exe in yt-web/ folder"})
    else:
        opts["ffmpeg_location"] = ffmpeg_exe

    # JS runtime — Python API uses extractor_args, not js_runtimes string
    js, js_msg = detect_js_runtime()
    q.put({"t": "log", "msg": js_msg})
    # Always set android fallback; if node/deno found it will also try web player
    clients = ["android", "web"] if not js else ["ios", "android", "web"]
    opts["extractor_args"] = {"youtube": {"player_client": clients}}

    if quality == "audio":
        opts["postprocessors"] = [{
            "key":              "FFmpegExtractAudio",
            "preferredcodec":   "mp3",
            "preferredquality": "0",
        }]
    else:
        opts["merge_output_format"] = "mp4"

    return opts


# ---------------------------------------------------------------------------
# Download worker
# ---------------------------------------------------------------------------

def _run(url: str, out_dir: str, quality: str, cookies_browser: str = ""):
    q    = _state["queue"]
    stop = _state["stop"]
    try:
        frozen = getattr(sys, "frozen", False)
        base   = Path(sys.executable).resolve().parent if frozen else Path(__file__).resolve().parent
        q.put({"t": "log", "msg": f"[debug] frozen={frozen} | base={base}"})
        q.put({"t": "log", "msg": f"[debug] yt-dlp {yt_dlp.version.__version__}"})

        Path(out_dir).mkdir(parents=True, exist_ok=True)
        opts = _build_opts(out_dir, quality, q, stop, cookies_browser)
        q.put({"t": "log", "msg": f"URL: {url}"})
        with yt_dlp.YoutubeDL(opts) as ydl:
            code = ydl.download([url])

        if stop.is_set():
            q.put({"t": "stopped"})
        elif code == 0:
            q.put({"t": "done"})
        else:
            q.put({"t": "error", "msg": f"yt-dlp exit code {code}"})

    except _StopSignal:
        q.put({"t": "stopped"})
    except yt_dlp.utils.DownloadError as e:
        if stop.is_set():
            q.put({"t": "stopped"})
        else:
            q.put({"t": "error", "msg": _clean(str(e))})
    except Exception as e:
        q.put({"t": "error", "msg": str(e)})
    finally:
        with _lock:
            _state["running"] = False


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    default = str(Path.home() / "Downloads").replace("\\", "/")
    return render_template("index.html", default_dir=default)


@app.route("/debug")
def debug():
    import shutil
    frozen = getattr(sys, "frozen", False)
    base   = Path(sys.executable).resolve().parent if frozen else Path(__file__).resolve().parent

    ffmpeg_exe, ffmpeg_msg = get_ffmpeg_exe()
    js, js_msg = detect_js_runtime()

    lines = [
        f"frozen        : {frozen}",
        f"base dir      : {base}",
        f"sys.executable: {sys.executable}",
        f"__file__      : {Path(__file__).resolve()}",
        f"",
        f"ffmpeg exe    : {ffmpeg_exe!r}",
        f"ffmpeg detail : {ffmpeg_msg}",
        f"",
        f"js runtime    : {js!r}",
        f"js detail     : {js_msg}",
        f"",
        f"yt-dlp        : {yt_dlp.version.__version__}",
        f"python        : {sys.version}",
        f"",
        "--- ffmpeg candidates ---",
    ]
    if frozen:
        candidates = [Path(sys.executable).resolve().parent]
    else:
        candidates = [base, base.parent]
    for d in candidates:
        for name in ("ffmpeg.exe", "ffmpeg"):
            p = d / name
            lines.append(f"  {p}  →  {'EXISTS' if p.exists() else 'missing'}")

    imageio_line = "imageio_ffmpeg: "
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        imageio_line += f"{exe}  →  {'EXISTS' if Path(exe).exists() else 'NOT ON DISK'}"
    except Exception as e:
        imageio_line += f"error: {e}"
    lines.append(imageio_line)

    system_ffmpeg = shutil.which("ffmpeg")
    lines.append(f"system ffmpeg : {system_ffmpeg or 'not in PATH'}")

    return "<pre style='font:13px monospace;padding:20px;background:#111;color:#cdd'>" + "\n".join(lines) + "</pre>"


@app.route("/browse", methods=["POST"])
def browse():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        current = (request.json or {}).get("current", str(Path.home()))
        path = filedialog.askdirectory(initialdir=current)
        root.destroy()
        return jsonify({"path": str(path).replace("\\", "/") if path else ""})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/open-folder", methods=["POST"])
def open_folder():
    try:
        folder = Path((request.json or {}).get("path", str(Path.home() / "Downloads")))
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(folder))
        elif sys.platform == "darwin":
            import subprocess; subprocess.run(["open", str(folder)])
        else:
            import subprocess; subprocess.run(["xdg-open", str(folder)])
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/download", methods=["POST"])
def start():
    with _lock:
        if _state["running"]:
            return jsonify({"error": "Already downloading"}), 400

        data    = request.json or {}
        url     = data.get("url", "").strip()
        out_dir = data.get("out_dir", str(Path.home() / "Downloads"))
        quality = data.get("quality", "best")
        cookies = data.get("cookies", "")

        if not url:
            return jsonify({"error": "No URL provided"}), 400

        # Flush old events
        while not _state["queue"].empty():
            try: _state["queue"].get_nowait()
            except queue.Empty: break

        _state["stop"].clear()
        _state["running"] = True

    threading.Thread(target=_run, args=(url, out_dir, quality, cookies), daemon=True).start()
    return jsonify({"ok": True})


@app.route("/stop", methods=["POST"])
def stop():
    _state["stop"].set()
    return jsonify({"ok": True})


@app.route("/events")
def events():
    def generate():
        q = _state["queue"]
        try:
            while True:
                try:
                    event = q.get(timeout=25)
                    yield f"data: {json.dumps(event)}\n\n"
                    if event["t"] in ("done", "error", "stopped"):
                        break
                except queue.Empty:
                    yield 'data: {"t":"ping"}\n\n'
        except GeneratorExit:
            pass

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5757")).start()
    app.run(host="127.0.0.1", port=5757, debug=False, threaded=True)
