#!/usr/bin/env python3
"""Run first: python preflight.py [input-path-or-url]. Prints host paths, route, capabilities, engine, todo.
`eval "$(python preflight.py --env)"` exports A UPLOADS WORK OUT."""
import os, re, socket, sys, tempfile
from pathlib import Path

A = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(A / "scripts" / "web"))
import webannotate as W  # noqa: E402
import static_engine as SE  # noqa: E402


def first_dir(*cands, write=True):
    for c in cands:
        if Path(c).is_dir() and os.access(c, os.W_OK if write else os.R_OK):
            return Path(c)


def route(a):
    if re.match(r"^https?://", a):
        u = re.sub(r"[?#].*$", "", a).lower()
        return "pdf-url" if u.endswith(".pdf") or "/pdf/" in u else "web"
    p = Path(a).expanduser()
    if not p.exists():
        return "unknown (file not found)"
    if b"%PDF-" in p.read_bytes()[:1024]:
        return "pdf"
    return "saved-page" if p.suffix.lower() in (".html", ".htm", ".zip") else "unknown (not a PDF or saved page; .mhtml: ask for .html/.zip)"


def has(mod):
    try:
        __import__(mod)
        return True
    except Exception:
        return False


def net(host):
    try:
        socket.getaddrinfo(host, 443)
    except Exception:
        return "dns-fail"
    try:
        socket.create_connection((host, 443), 3).close()
        return "ok"
    except Exception:
        return "blocked"


def main():
    rt = "claude" if Path("/mnt/user-data").exists() else "chatgpt" if Path("/mnt/data").exists() else "local"
    up = first_dir("/mnt/user-data/uploads", "/mnt/data", Path.cwd(), write=False)
    out = first_dir("/mnt/user-data/outputs", "/mnt/data", Path.cwd())
    work = Path(first_dir("/home/claude", "/mnt/data", tempfile.gettempdir())) / "annotator_work"
    work.mkdir(exist_ok=True)
    if "--env" in sys.argv:
        return print(f'export A="{A}" UPLOADS="{up}" WORK="{work}" OUT="{out}"')
    print(f"runtime={rt} A={A} UPLOADS={up} WORK={work} OUT={out}")
    args = [x for x in sys.argv[1:] if not x.startswith("--")]
    if args:
        print("route=" + route(args[0]))
    pym, pil = has("pymupdf") or has("fitz"), has("PIL")
    ok, cat, detail = W.browser_status()
    svg, exe, nodes = SE.svg_rasterizer_available(), W.find_chromium(), has("playwright")
    inet = net("example.com")
    pip = net("pypi.org")
    if args and route(args[0]) in ("web", "pdf-url"):
        import urllib.parse
        h = urllib.parse.urlparse(args[0]).hostname
        print(f"url_host={h}:{net(h)}")
    engine = "browser" if ok and pil else "static" if pil else "none"
    print(f"cap: pymupdf={pym} pillow={pil} playwright={nodes} browser={cat} system_chromium={exe or 'none'} svg={svg or 'none'} internet={inet} pip_index={pip}")
    if detail and not ok:
        print(f"browser_error: {detail}")
    print(f"engine={engine} ready: pdf={pym} saved_page={engine != 'none'} url={ok and pil and inet == 'ok'}")
    todo = []
    if not pym:
        todo.append("pip install pymupdf (PDF route)")
    if not pil:
        todo.append("pip install pillow (saved-page route)")
    if not svg:
        todo.append("pip install pymupdf or cairosvg (else SVG figures are not viewable: declare them unavailable)")
    if cat == "playwright_missing":
        todo.append("only for URLs/PDF output/browser QA: pip install playwright; python -m playwright install chromium (or set ANNOTATOR_CHROMIUM_PATH)")
    elif cat == "browser_binary_missing":
        todo.append("only for URLs/PDF output/browser QA: python -m playwright install chromium, or install system Chromium, or set ANNOTATOR_CHROMIUM_PATH")
    elif cat == "system_libs_missing":
        todo.append("browser libs missing: python -m playwright install-deps chromium (root)")
    if engine == "static":
        todo.append("static engine: no page JS/CSS layout/canvas/iframe/video/PDF output; browser visual QA = NOT RUN")
    if args and route(args[0]) == "web" and not (ok and inet == "ok"):
        todo.append("live URL not possible: allow the host (Claude: Settings > Capabilities > Domain allowlist) or ask for a saved page (.html/.zip) or PDF")
    if not any(Path(p).exists() for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",)):
        todo.append("non-English PDF text: pass --font <ttf>")
    for t in todo:
        print("todo:", t)


if __name__ == "__main__":
    main()
