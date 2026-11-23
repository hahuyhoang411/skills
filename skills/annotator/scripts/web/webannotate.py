#!/usr/bin/env python3
"""webannotate: turn any web page / blog post into a fully-read, annotated copy.

  fetch  <url>   render the page in Chromium, extract text + every figure (PNG, GIF/video frames)
  check  <dir>   verify annotations.json: full-read coverage, anchors really exist, schema
  render <dir>   build annotated.pdf, annotated.html (offline-safe snapshot) and annotated.user.js

Typical run (Claude does the middle step):  fetch -> read everything -> write annotations.json -> check -> render
"""
import argparse, base64, json, re, sys, datetime, urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
JS = HERE / "js"
NOTE_TYPES = {"CONCERN", "VERIFY", "SPECULATION", "NOTE", "CHECKED", "STRENGTH"}


# ---------------------------------------------------------------- helpers
def slugify(s, n=48):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n] or "page"


def norm_url(arg):
    if re.match(r"^(https?|file)://", arg):
        return arg
    p = Path(arg).expanduser()
    if p.exists():
        return p.resolve().as_uri()
    return "https://" + arg


def resolve_local(lp, out):
    """Saved page: a single .html (e.g. SingleFile) or a .zip of 'Webpage, complete'. Returns a file:// URL."""
    if lp.suffix.lower() == ".zip":
        import zipfile
        dest = out / "source"
        with zipfile.ZipFile(lp) as z:
            z.extractall(dest)
        htmls = sorted([h for h in dest.rglob("*") if h.suffix.lower() in (".html", ".htm")],
                       key=lambda h: (not h.name.lower().startswith("index"), len(h.parts), -h.stat().st_size))
        if not htmls:
            raise SystemExit("no .html file found inside the zip")
        return htmls[0].resolve().as_uri()
    return lp.resolve().as_uri()


def browser_opts(args):
    """Use the environment's proxy (HTTPS_PROXY etc.) when one is configured, as cloud sandboxes do.
    --insecure-tls only skips certificate checks (for TLS-inspecting proxies); use for reading public pages only."""
    import os
    launch, ctx = {}, {"bypass_csp": True}
    raw = None if getattr(args, "no_proxy", False) else (
        os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"))
    if raw:
        u = urllib.parse.urlparse(raw)
        d = {"server": f"{u.scheme or 'http'}://{u.hostname}:{u.port or (443 if u.scheme == 'https' else 80)}"}
        if u.username:
            d["username"] = urllib.parse.unquote(u.username)
            d["password"] = urllib.parse.unquote(u.password or "")
        np = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
        if np:
            d["bypass"] = np
        launch["proxy"] = d
    if getattr(args, "insecure_tls", False):
        ctx["ignore_https_errors"] = True
    return launch, ctx


def read_js(name):
    return (JS / name).read_text(encoding="utf-8")


def autoscroll(page, max_steps=200):
    page.evaluate(
        """async (maxSteps) => {
          document.querySelectorAll('img[loading=lazy]').forEach(i => i.loading = 'eager');
          await new Promise(res => {
            let y = 0, n = 0;
            const t = setInterval(() => {
              window.scrollBy(0, 600); y += 600; n++;
              if (y >= document.documentElement.scrollHeight + 600 || n >= maxSteps) {
                clearInterval(t); window.scrollTo(0, 0); res();
              }
            }, 120);
          });
        }""",
        max_steps,
    )


def load_page(page, url, wait=2.0, timeout=45):
    page.goto(url, wait_until="load", timeout=timeout * 1000)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    autoscroll(page)
    try:
        page.wait_for_function("[...document.images].every(i => i.complete)", timeout=10000)
    except Exception:
        pass
    page.wait_for_timeout(int(wait * 1000))
    page.evaluate(read_js("common.js"))


def get_bytes(ctx, src):
    if src.startswith("data:"):
        head, _, data = src.partition(",")
        return base64.b64decode(data) if ";base64" in head else urllib.parse.unquote_to_bytes(data)
    if src.startswith("file://"):
        return Path(urllib.parse.unquote(urllib.parse.urlparse(src).path)).read_bytes()
    r = ctx.request.get(src, timeout=20000)
    if not r.ok:
        raise RuntimeError(f"HTTP {r.status}")
    return r.body()


def sample_indices(n, k):
    if n <= k:
        return list(range(n))
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


def gif_frames(raw, out_prefix, k):
    """Return (frames, is_animated). Works for GIF / animated WebP / APNG via Pillow."""
    import io
    from PIL import Image, ImageSequence

    im = Image.open(io.BytesIO(raw))
    n = getattr(im, "n_frames", 1)
    if n <= 1:
        return [], False
    durs, t = [], 0.0
    for fr in ImageSequence.Iterator(im):
        durs.append(t)
        t += (fr.info.get("duration", 100) or 100) / 1000.0
    frames = []
    for j, idx in enumerate(sample_indices(n, k), 1):
        im.seek(idx)
        p = Path(f"{out_prefix}.frame{j:02d}.png")
        im.convert("RGBA").save(p)
        frames.append({"i": j, "src_frame": idx, "t": round(durs[idx], 2), "file": p.name})
    return frames, True


# ---------------------------------------------------------------- fetch
def cmd_fetch(a):
    from playwright.sync_api import sync_playwright

    lp = Path(a.url).expanduser()
    if not re.match(r"^(https?|file)://", a.url) and lp.exists():
        out = Path(a.out or f"wa_{slugify(lp.stem)}")
        (out / "figures").mkdir(parents=True, exist_ok=True)
        url = resolve_local(lp, out)
    else:
        url = norm_url(a.url)
        host = urllib.parse.urlparse(url).netloc or "local"
        out = Path(a.out or f"wa_{slugify(host + '-' + urllib.parse.urlparse(url).path)}")
        (out / "figures").mkdir(parents=True, exist_ok=True)
    failed_hosts = set()

    with sync_playwright() as p:
        lo, co = browser_opts(a)
        br = p.chromium.launch(**lo)
        ctx = br.new_context(viewport={"width": a.width, "height": a.height}, **co)
        page = ctx.new_page()
        load_page(page, url, a.wait)
        page.evaluate(read_js("extract.js"))
        data = page.evaluate("window.__WA_EXTRACT__()")

        for f in data["figures"]:
            fid = f["id"]
            loc = page.locator(f'[data-wa-id="{fid}"]').first
            png = out / "figures" / f"{fid}.png"
            try:
                loc.scroll_into_view_if_needed(timeout=5000)
                loc.screenshot(path=str(png), timeout=15000)
                f["file"] = f"figures/{png.name}"
            except Exception as e:  # keep going, record the problem
                f["error"] = f"screenshot failed: {str(e)[:120]}"
            if f["kind"] == "img" and not f.get("natural_w"):
                f["error"] = "image did not load (blocked host or broken link)"
                h = urllib.parse.urlparse(f["src"]).netloc
                if h:
                    failed_hosts.add(h)
            f["frames"] = []
            prefix = str(out / "figures" / fid)
            try:
                if f["kind"] == "img" and f["src"]:
                    raw = get_bytes(ctx, f["src"])
                    frames, animated = gif_frames(raw, prefix, a.frames)
                    if animated:
                        f["kind"] = "animated"
                        f["frames"] = [dict(fr, file=f"figures/{fr['file']}") for fr in frames]
                elif f["kind"] == "video" and f.get("duration"):
                    k = min(a.frames, max(2, int(f["duration"])))
                    for j in range(k):
                        t = round(f["duration"] * j / max(1, k - 1) * 0.98, 2)
                        page.evaluate(
                            """([id, t]) => new Promise(res => {
                                 const v = document.querySelector(`[data-wa-id="${id}"]`);
                                 v.pause();
                                 const done = () => { v.removeEventListener('seeked', done); res(true); };
                                 v.addEventListener('seeked', done); v.currentTime = t;
                                 setTimeout(() => res(false), 4000);
                               })""",
                            [fid, t],
                        )
                        fp = out / "figures" / f"{fid}.frame{j + 1:02d}.png"
                        loc.screenshot(path=str(fp), timeout=15000)
                        f["frames"].append({"i": j + 1, "t": t, "file": f"figures/{fp.name}"})
            except Exception as e:
                f["frame_error"] = str(e)[:120]
            if f["kind"] == "embed":
                f["note"] = "embedded iframe: only its outer appearance is captured, contents not inspectable"

        if not a.no_pdf:
            try:
                page.emulate_media(media="print")
                page.pdf(path=str(out / "page.pdf"), print_background=True, format="A4")
            except Exception as e:
                print("pdf skipped:", str(e)[:100])
        br.close()

    manifest = {
        "url": url, "title": data["title"], "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "paragraphs": data["paragraphs"], "figures": data["figures"], "order": data["order"],
        "failed_image_hosts": sorted(failed_hosts),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")

    pmap = {x["id"]: x for x in data["paragraphs"]}
    fmap = {x["id"]: x for x in data["figures"]}
    lines = [f"# {data['title']}", f"source: {url}", f"paragraphs: {len(pmap)}   figures: {len(fmap)}", ""]
    for i in data["order"]:
        if i in pmap:
            lines.append(f"[{i}] {pmap[i]['text']}")
        else:
            f = fmap[i]
            fr = f" frames={len(f['frames'])}" if f["frames"] else ""
            lines.append(f"\n[FIGURE {i} kind={f['kind']}{fr} {f['natural_w'] or f['w']}x{f['natural_h'] or f['h']}] "
                         f"alt={f['alt']!r} caption={f['caption']!r}  file={f.get('file', 'MISSING')}\n")
    (out / "article.md").write_text("\n".join(lines), encoding="utf-8")

    bad = [f["id"] for f in data["figures"] if "error" in f or not f.get("file")]
    print(f"bundle: {out}/")
    print(f"  paragraphs={len(pmap)} figures={len(fmap)} "
          f"animated={sum(1 for f in fmap.values() if f['frames'])} embeds={sum(1 for f in fmap.values() if f['kind'] == 'embed')}")
    if bad:
        print("  WARNING figures without screenshot:", ", ".join(bad))
    if failed_hosts:
        print("  WARNING images failed to load from: " + ", ".join(sorted(failed_hosts)))
        print("    -> allow these hosts in the network allowlist, or fetch from a saved copy of the page (.html/.zip)")
    if not pmap:
        print("  WARNING no paragraphs extracted: page may be blocked, paywalled or need login")
    return 0


# ---------------------------------------------------------------- check
def parse_ids(spec, prefix):
    ids = set()
    for part in re.split(r"[,\s]+", spec or ""):
        if not part:
            continue
        m = re.match(rf"^{prefix}(\d+)-{prefix}?(\d+)$", part)
        if m:
            ids.update(f"{prefix}{i}" for i in range(int(m[1]), int(m[2]) + 1))
        elif re.match(rf"^{prefix}\d+$", part):
            ids.add(part)
    return ids


def run_check(d, ann_path=None, quiet=False):
    man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    ann = json.loads((ann_path or d / "annotations.json").read_text(encoding="utf-8"))
    errs, warns = [], []
    paras = man["paragraphs"]
    figs = {f["id"]: f for f in man["figures"]}
    cov = ann.get("coverage", {})

    read = parse_ids(cov.get("paragraphs_read", ""), "p")
    allp = {p["id"] for p in paras}
    miss = sorted(allp - read, key=lambda x: int(x[1:]))
    if miss:
        errs.append(f"text not fully read: {len(miss)}/{len(allp)} paragraphs missing from coverage.paragraphs_read (e.g. {', '.join(miss[:8])})")

    viewed = set(cov.get("figures_viewed", []))
    unavail = set(cov.get("figures_unavailable", []))
    fv = cov.get("frames_viewed", {})
    for fid, f in figs.items():
        bad = ("error" in f and "did not load" in f["error"]) or not f.get("file")
        if bad:
            why = f.get("error", "no screenshot")
            if fid in unavail:
                warns.append(f"{fid} unavailable ({why}); declared in figures_unavailable, say so in the summary")
            else:
                errs.append(f"{fid}: image unavailable ({why}). Fix access, or declare it in coverage.figures_unavailable")
            continue
        if fid not in viewed:
            errs.append(f"figure {fid} not viewed ({f['kind']}, {f.get('file', 'no file')})")
        need = {fr["i"] for fr in f.get("frames", [])}
        if need and not need <= set(fv.get(fid, [])):
            errs.append(f"{fid}: frames {sorted(need - set(fv.get(fid, [])))} not viewed")
        if f["kind"] == "embed":
            warns.append(f"{fid} is an embed (iframe): contents could not be inspected, say so in the notes")
        if "frame_error" in f:
            warns.append(f"{fid}: {f['frame_error']}")

    texts = [" ".join(p["text"].split()) for p in paras]
    keys = set()
    notes = ann.get("notes", [])
    for n in notes:
        k = n.get("key")
        if not k or k in keys:
            errs.append(f"note key missing or duplicated: {k!r}")
        keys.add(k)
        if n.get("type") not in NOTE_TYPES:
            errs.append(f"{k}: type must be one of {sorted(NOTE_TYPES)}")
        if not n.get("note"):
            errs.append(f"{k}: empty note")
        if n.get("figure"):
            if n["figure"] not in figs:
                errs.append(f"{k}: unknown figure {n['figure']}")
            b = n.get("box")
            if b is not None and not (len(b) == 4 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in b) and b[0] + b[2] <= 1.001 and b[1] + b[3] <= 1.001):
                errs.append(f"{k}: box must be [x,y,w,h] normalised to 0..1 and inside the figure")
            fr = n.get("frame")
            if fr and fr not in {x["i"] for x in figs.get(n["figure"], {}).get("frames", [])}:
                errs.append(f"{k}: frame {fr} does not exist for {n['figure']}")
        else:
            q = " ".join((n.get("quote") or "").split())
            if not q:
                errs.append(f"{k}: needs a 'quote' anchor (or a 'figure')")
                continue
            if len(q.split()) > 15:
                warns.append(f"{k}: anchor is {len(q.split())} words; keep anchors short (<15) and notes in your own words")
            hits = sum(t.count(q) for t in texts)
            if hits == 0:
                errs.append(f"{k}: anchor not found in page text: {q!r}")
            elif hits > 1:
                warns.append(f"{k}: anchor occurs {hits} times, the first one will be used")
    for n in notes:
        for l in n.get("links", []):
            if l not in keys:
                errs.append(f"{n.get('key')}: link to unknown note {l!r}")

    n_fig_notes = sum(1 for n in notes if n.get("figure"))
    if not quiet:
        nf = len(figs)
        print(f"coverage: paragraphs {len(allp & read)}/{len(allp)}  figures {len(viewed & set(figs))}/{nf - len(unavail & set(figs))}"
              f"{f' (+{len(unavail & set(figs))} unavailable)' if unavail & set(figs) else ''}  "
              f"animated frames viewed {sum(len(fv.get(i, [])) for i in figs)}/{sum(len(f.get('frames', [])) for f in figs.values())}")
        print(f"notes: {len(notes)} ({n_fig_notes} on figures)")
        for w in warns:
            print("  warn:", w)
        for e in errs:
            print("  ERROR:", e)
        print("RESULT:", "OK" if not errs else f"{len(errs)} problem(s)")
    return errs, warns, man, ann


def cmd_check(a):
    errs, *_ = run_check(Path(a.dir), Path(a.annotations) if a.annotations else None)
    return 1 if errs else 0


# ---------------------------------------------------------------- render
def frame_data_uri(path, max_w=520):
    import io
    from PIL import Image
    im = Image.open(path).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def cmd_render(a):
    from playwright.sync_api import sync_playwright

    d = Path(a.dir)
    errs, warns, man, ann = run_check(d, Path(a.annotations) if a.annotations else None, quiet=True)
    if errs and not a.force:
        print("check failed, fix these first (or pass --force):")
        for e in errs:
            print("  ERROR:", e)
        return 1
    figs = {f["id"]: f for f in man["figures"]}
    notes = []
    for n in ann["notes"]:
        n = dict(n)
        if n.get("figure"):
            f = figs[n["figure"]]
            n.update(fig_src=f["src"], fig_index=f["index"], fig_frames=len(f.get("frames", [])) or None)
            fr = next((x for x in f.get("frames", []) if x["i"] == n.get("frame")), None)
            if fr:
                n["frame_t"] = fr["t"]
                n["frame_img"] = frame_data_uri(d / fr["file"])
        notes.append(n)
    WA = {"title": ann.get("title") or man["title"], "summary": ann.get("summary", ""), "notes": notes}
    wa_json = json.dumps(WA, ensure_ascii=False).replace("</", "<\\/")
    common, overlay = read_js("common.js"), read_js("overlay.js")

    with sync_playwright() as p:
        lo, co = browser_opts(a)
        br = p.chromium.launch(**lo)
        ctx = br.new_context(viewport={"width": a.width, "height": a.height}, **co)
        page = ctx.new_page()
        load_page(page, man["url"], a.wait)

        # 1) static HTML snapshot (scripts removed so the site cannot wipe the overlay; overlay runs on open)
        html = page.content()
        html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S | re.I)
        html = re.sub(r"(<head[^>]*>)", r'\1<base href="%s">' % man["url"], html, count=1, flags=re.I)
        boot = ("<script>window.__WA__=%s;</script><script>%s</script><script>%s</script>"
                "<script>(function(){var n=0,iv=setInterval(function(){n++;"
                "if(document.readyState==='complete'||n>20){clearInterval(iv);window.__WA_START__();}},400);})();</script>"
                % (wa_json, common, overlay))
        html = html.replace("</body>", boot + "</body>") if "</body>" in html else html + boot
        only = getattr(a, "only", None)
        if only != "pdf":
            (d / "annotated.html").write_text(html, encoding="utf-8")

        # 2) live overlay -> annotated PDF (status is computed either way)
        page.evaluate("window.__WA__ = " + json.dumps(WA, ensure_ascii=False))
        page.evaluate(overlay)
        status = page.evaluate("window.__WA_START__()")
        page.wait_for_timeout(500)
        if only != "html":
            page.emulate_media(media="print")
            page.pdf(path=str(d / "annotated.pdf"), print_background=True, format="A4",
                     margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"})
        br.close()

    # 3) userscript for live reading on the real site
    u = urllib.parse.urlparse(man["url"])
    if u.scheme in ("http", "https") and not only:
        us = ("// ==UserScript==\n// @name         Annotations: %s\n// @namespace    webannotate\n// @version      1.0\n"
              "// @match        %s://%s%s*\n// @grant        none\n// @run-at       document-idle\n// ==/UserScript==\n"
              "window.__WA__=%s;\n%s\n%s\n(function(){var n=0,iv=setInterval(function(){n++;"
              "if(document.readyState==='complete'||n>20){clearInterval(iv);window.__WA_START__();}},500);})();\n"
              % (WA["title"][:60].replace("\n", " "), u.scheme, u.netloc, u.path, wa_json, common, overlay))
        (d / "annotated.user.js").write_text(us, encoding="utf-8")

    print(f"anchored {status['anchored']}/{status['total']}" + (f"  MISSED: {status['missed']}" if status["missed"] else ""))
    print("wrote:", ", ".join(x for x in ["annotated.pdf", "annotated.html", "annotated.user.js"] if (d / x).exists()))
    return 0 if not status["missed"] else 2


# ---------------------------------------------------------------- doctor
def cmd_doctor(a):
    import socket
    ok = True
    try:
        import playwright  # noqa: F401
        from PIL import Image  # noqa: F401
        print("python deps: ok")
    except Exception as e:
        print("python deps: MISSING ->", e, "\n  pip install playwright pillow --break-system-packages && playwright install chromium")
        return 1
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        print("chromium: ok")
    except Exception as e:
        print("chromium: FAILED ->", str(e).split("\n")[0][:150])
        ok = False
    if a.url and re.match(r"^https?://", a.url):
        pu = urllib.parse.urlparse(a.url)
        host, port = pu.hostname, pu.port or (443 if pu.scheme == "https" else 80)
        try:
            socket.getaddrinfo(host, port)
            socket.create_connection((host, port), timeout=8).close()
            print(f"network: {host} reachable")
        except Exception as e:
            ok = False
            print(f"network: {host} BLOCKED ({e.__class__.__name__}).")
            print("  Allow it in claude.ai > Settings > Capabilities > Domain allowlist > Additional allowed domains,")
            print("  or use a saved copy of the page: python webannotate.py fetch saved_page.html|.zip")
    print("READY" if ok else "NOT READY")
    return 0 if ok else 1


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(prog="webannotate", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="render a page and extract text, figures, GIF/video frames")
    f.add_argument("url", help="URL, or a saved page: local .html / .zip")
    f.add_argument("--out", help="bundle folder (default wa_<slug>)")
    f.add_argument("--frames", type=int, default=6, help="max frames sampled per GIF/video")
    f.add_argument("--wait", type=float, default=2.0, help="extra settle time in seconds")
    f.add_argument("--width", type=int, default=1280)
    f.add_argument("--height", type=int, default=900)
    f.add_argument("--no-pdf", action="store_true")
    f.add_argument("--insecure-tls", action="store_true", help="skip TLS certificate checks (TLS-inspecting proxy)")
    f.add_argument("--no-proxy", action="store_true", help="ignore HTTPS_PROXY/HTTP_PROXY env vars")
    f.set_defaults(fn=cmd_fetch)
    dd = sub.add_parser("doctor", help="check deps, Chromium and (optionally) whether a URL is reachable")
    dd.add_argument("url", nargs="?")
    dd.set_defaults(fn=cmd_doctor)
    c = sub.add_parser("check", help="verify coverage + anchors in annotations.json")
    c.add_argument("dir")
    c.add_argument("--annotations")
    c.set_defaults(fn=cmd_check)
    r = sub.add_parser("render", help="write annotated.pdf / annotated.html / annotated.user.js")
    r.add_argument("dir")
    r.add_argument("--annotations")
    r.add_argument("--wait", type=float, default=2.0)
    r.add_argument("--width", type=int, default=1100)
    r.add_argument("--height", type=int, default=900)
    r.add_argument("--only", choices=["html", "pdf"], help="write just that file (html: annotated.html only; pdf: annotated.pdf only); default writes all three")
    r.add_argument("--force", action="store_true", help="render even if check reports problems")
    r.add_argument("--insecure-tls", action="store_true")
    r.add_argument("--no-proxy", action="store_true")
    r.set_defaults(fn=cmd_render)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
