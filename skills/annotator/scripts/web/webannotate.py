#!/usr/bin/env python3
"""webannotate: fetch -> (read, annotate) -> check -> render. Engines: browser (Chromium via Python Playwright; system Chromium reused) and
static (saved .html/.zip, no browser). Same bundle, ids, overlay and gates in both.

  fetch <url|saved.html|saved.zip> [--engine auto|browser|static]   (ANNOTATOR_ENGINE=static forces static)
  check <dir>      render <dir> [--only html|pdf] [--engine static]
"""
import argparse, base64, hashlib, json, re, shutil, subprocess, sys, datetime, urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import gates  # scripts/gates.py: passes validation + note lint
import static_engine as SE
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


def safe_extract_zip(lp, dest):
    """Extract a saved-page zip; refuse entries that would land outside `dest` (zip-slip) and absurd sizes."""
    import zipfile
    dest = dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    total = 0
    with zipfile.ZipFile(lp) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if dest != target and dest not in target.parents:
                raise SystemExit(f"refusing zip: entry escapes the extraction folder ({info.filename!r})")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise SystemExit(f"refusing zip: symbolic link entry ({info.filename!r})")
            total += info.file_size
            if total > 800 * 1024 * 1024:
                raise SystemExit("refusing zip: more than 800 MB when extracted")
        z.extractall(dest)
    return dest


def pick_html(dest):
    htmls = sorted([h for h in dest.rglob("*") if h.suffix.lower() in (".html", ".htm")],
                   key=lambda h: (not h.name.lower().startswith("index"), len(h.parts), -h.stat().st_size))
    if not htmls:
        raise SystemExit("no .html file found inside the zip")
    return htmls[0]


def resolve_local(lp, out):
    """Saved page: a single .html (e.g. SingleFile) or a .zip of 'Webpage, complete'. Returns a file:// URL."""
    if lp.suffix.lower() == ".zip":
        return pick_html(safe_extract_zip(lp, out / "source")).resolve().as_uri()
    return lp.resolve().as_uri()


def find_chromium():
    """System Chromium/Chrome path: ANNOTATOR_CHROMIUM_PATH, PLAYWRIGHT_CHROMIUM_EXECUTABLE, PATH, common install locations."""
    import os
    for v in ("ANNOTATOR_CHROMIUM_PATH", "PLAYWRIGHT_CHROMIUM_EXECUTABLE"):
        if os.environ.get(v) and Path(os.environ[v]).exists():
            return os.environ[v]
    for n in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        if shutil.which(n):
            return shutil.which(n)
    for c in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome", "/opt/google/chrome/chrome", "/snap/bin/chromium",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        if Path(c).exists():
            return c
    return None


def launch(p, **opts):
    """Chromium via Python Playwright: ANNOTATOR_CHROMIUM_PATH if set, else Playwright's managed browser, else system Chromium/Chrome."""
    import os
    if os.environ.get("ANNOTATOR_CHROMIUM_PATH") and Path(os.environ["ANNOTATOR_CHROMIUM_PATH"]).exists():
        return p.chromium.launch(executable_path=os.environ["ANNOTATOR_CHROMIUM_PATH"], **opts)
    try:
        return p.chromium.launch(**opts)
    except Exception as e:
        exe = find_chromium()
        if exe and ("Executable doesn't exist" in str(e) or "playwright install" in str(e)):
            return p.chromium.launch(executable_path=exe, **opts)
        raise


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


# ---------------------------------------------------------------- engines
def browser_status():
    """Granular: returns (ok, category, detail). Categories: ok | playwright_missing | browser_binary_missing |
    system_libs_missing | launch_failed | disabled. A launch failure is never reported as DNS: DNS belongs to the network check."""
    import os
    if os.environ.get("ANNOTATOR_ENGINE") == "static":
        return False, "disabled", "ANNOTATOR_ENGINE=static"
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        return False, "playwright_missing", f"python package not importable: {str(e)[:100]}"
    try:
        with sync_playwright() as p:
            launch(p).close()
        return True, "ok", "chromium launches"
    except Exception as e:
        msg = str(e).strip().splitlines()[0][:160] if str(e).strip() else e.__class__.__name__
        full = str(e)
        if "Executable doesn't exist" in full or "playwright install" in full:
            return False, "browser_binary_missing", msg
        if "missing dependencies" in full or "error while loading shared libraries" in full:
            return False, "system_libs_missing", msg
        return False, "launch_failed", msg


def is_saved_page(arg):
    p = Path(arg).expanduser()
    return not re.match(r"^(https?|file)://", arg) and p.exists() and p.suffix.lower() in (".html", ".htm", ".zip")


def choose_fetch_engine(a):
    eng = getattr(a, "engine", "auto")
    if eng == "static":
        return "static", None
    ok, cat, detail = (True, "ok", "") if eng == "browser" else browser_status()
    if ok:
        return "browser", None
    if is_saved_page(a.url):
        return "static", f"browser unavailable ({cat}: {detail}); using the browserless static engine for this saved page"
    raise SystemExit(f"browser unavailable ({cat}: {detail}). A live URL needs a browser: install Chromium (playwright install chromium) "
                     "or upload a saved page (.html/.zip) or a PDF print. Not falling back to a look-alike.")


# ---------------------------------------------------------------- fetch
def cmd_fetch(a):
    eng, why = choose_fetch_engine(a)
    if eng == "static":
        return cmd_fetch_static(a, why)
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
        br = launch(p, **lo)
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

    return write_bundle(out, url, data, failed_hosts, "browser", {}, a)


def write_bundle(out, url, data, failed_hosts, engine, extra, a):
    manifest = {
        "url": url, "title": data["title"], "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "engine": engine, "paragraphs": data["paragraphs"], "figures": data["figures"], "order": data["order"],
        "failed_image_hosts": sorted(failed_hosts), **extra,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")

    pmap = {x["id"]: x for x in data["paragraphs"]}
    fmap = {x["id"]: x for x in data["figures"]}
    lines = [f"# {data['title']}", f"source: {url}", f"engine: {engine}", f"paragraphs: {len(pmap)}   figures: {len(fmap)}", ""]
    for i in data["order"]:
        if i in pmap:
            lines.append(f"[{i}] {pmap[i]['text']}")
        else:
            f = fmap[i]
            fr = f" frames={len(f['frames'])}" if f["frames"] else ""
            lines.append(f"\n[FIGURE {i} kind={f['kind']}{fr} {f['natural_w'] or f['w']}x{f['natural_h'] or f['h']}] "
                         f"alt={f['alt']!r} caption={f['caption']!r}  file={f.get('file', 'MISSING')}"
                         + (f"  render={f['render']!r}" if f.get("render") else "")
                         + (f"  UNAVAILABLE={f['error']!r}" if f.get("error") and not f.get("file") else "") + "\n")
    (out / "article.md").write_text("\n".join(lines), encoding="utf-8")

    bad = [f["id"] for f in data["figures"] if "error" in f or not f.get("file")]
    print(f"bundle: {out}/   engine={engine}")
    print(f"  paragraphs={len(pmap)} figures={len(fmap)} "
          f"animated={sum(1 for f in fmap.values() if f['frames'])} embeds={sum(1 for f in fmap.values() if f['kind'] == 'embed')}")
    for f in data["figures"]:
        print(f"  {f['id']}: {f['kind']:<10} {'PNG' if f.get('file') else 'NO IMAGE'}  {f.get('render') or f.get('error') or ''}"[:200])
    if bad:
        print("  WARNING figures without a viewable image (declare them in coverage.figures_unavailable / pass2.figures inspected:false):",
              ", ".join(bad))
    if failed_hosts:
        print("  WARNING images failed to load from: " + ", ".join(sorted(failed_hosts)))
        print("    -> allow these hosts in the network allowlist, or fetch from a saved copy of the page (.html/.zip)")
    if not pmap:
        print("  WARNING no paragraphs extracted: page may be blocked, paywalled, need login, or be built by JavaScript (static engine cannot run JS)")
    return 0


def cmd_fetch_static(a, why=None):
    """Browserless extraction of a saved page (.html / webpage-complete .zip). No Playwright, no Chromium."""
    if why:
        print("NOTE:", why)
    arg = a.url
    lp = Path(arg).expanduser()
    live = re.match(r"^https?://", arg) is not None
    if live:
        url = norm_url(arg)
        out = Path(a.out or f"wa_{slugify(urllib.parse.urlparse(url).netloc + '-' + urllib.parse.urlparse(url).path)}")
        (out / "figures").mkdir(parents=True, exist_ok=True)
        try:
            raw, _ = SE.load_bytes(url, out, url)
        except Exception as e:
            raise SystemExit(f"could not download {url}: {e.__class__.__name__}: {str(e)[:100]}. "
                             "Upload a saved page (.html/.zip) or a PDF print; no proxy/mirror workaround is attempted.")
        src_dir = out / "source"; src_dir.mkdir(exist_ok=True)
        (src_dir / "page.html").write_bytes(raw)
        html_path, root, base_url = src_dir / "page.html", src_dir, url
        print("WARNING: live URL fetched as raw HTML without running JavaScript; content rendered by scripts is missing. "
              "Say this in the summary.")
    else:
        if not lp.exists():
            raise SystemExit(f"not found: {arg}")
        out = Path(a.out or f"wa_{slugify(lp.stem)}")
        (out / "figures").mkdir(parents=True, exist_ok=True)
        src_dir = out / "source"
        if lp.suffix.lower() == ".zip":
            root = safe_extract_zip(lp, src_dir)
            html_path = pick_html(root)
        else:
            src_dir.mkdir(exist_ok=True)
            html_path = src_dir / lp.name
            shutil.copyfile(lp, html_path)
            root = src_dir
        base_url = html_path.resolve().as_uri()
    raw_html = html_path.read_bytes()
    src_html = raw_html.decode("utf-8", "replace")
    enc = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw_html[:4096], re.I)
    if enc and enc.group(1).lower() not in (b"utf-8", b"utf8"):
        try:
            src_html = raw_html.decode(enc.group(1).decode())
        except Exception:
            pass
    (out / "figures").mkdir(parents=True, exist_ok=True)
    data, _ = SE.extract(src_html, out, html_path.parent, base_url, a.frames, gif_frames, root=root)
    failed_hosts = set()
    for f in data["figures"]:
        if "did not load" in (f.get("error") or ""):
            h = urllib.parse.urlparse(f.get("src") or "").netloc
            if h:
                failed_hosts.add(h)
    extra = {"static": {"html": str(html_path.resolve().relative_to(out.resolve())), "root": str(Path(root).resolve().relative_to(out.resolve())),
                        "sha256": hashlib.sha256(raw_html).hexdigest(), "svg_renderer": SE.svg_rasterizer_available() or None}}
    return write_bundle(out, base_url, data, failed_hosts, "static", extra, a)


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


def run_check(d, ann_path=None, quiet=False, passes_path=None):
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

    n_src_e, n_src_w = len(errs), len(warns)
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

    n_anc_e, n_anc_w = len(errs), len(warns)

    # analytical quality: three-pass record + note substance (scripts/gates.py)
    pp = Path(passes_path) if passes_path else d / "passes.json"
    good_figs = [fid for fid, f in figs.items() if f.get("file") and "did not load" not in (f.get("error") or "")
                 and fid not in unavail]
    high = [n.get("key") for n in notes if n.get("pri") == "high" and n.get("key")]
    if not pp.exists():
        errs.append(f"passes.json missing at {pp}: record the three passes, evidence ledger and figure inspections first (references/gates.md)")
    else:
        try:
            qe, qw = gates.validate_passes(json.loads(pp.read_text(encoding="utf-8")), good_figs, high)
            errs += qe; warns += qw
        except Exception as ex:
            errs.append(f"passes.json unreadable: {ex}")
    qe, qw = gates.lint_notes(notes, len(paras))
    errs += qe; warns += qw

    n_fig_notes = sum(1 for n in notes if n.get("figure"))
    if not quiet:
        nf = len(figs)
        print(f"coverage: paragraphs {len(allp & read)}/{len(allp)}  figures {len(viewed & set(figs))}/{nf - len(unavail & set(figs))}"
              f"{f' (+{len(unavail & set(figs))} unavailable)' if unavail & set(figs) else ''}  "
              f"animated frames viewed {sum(len(fv.get(i, [])) for i in figs)}/{sum(len(f.get('frames', [])) for f in figs.values())}")
        print(f"notes: {len(notes)} ({n_fig_notes} on figures)")
        for title, a, b, wa, wb in (("1 SOURCE COVERAGE", 0, n_src_e, 0, n_src_w),
                                    ("2 ANCHORS AND SCHEMA", n_src_e, n_anc_e, n_src_w, n_anc_w),
                                    ("3 ANALYTICAL QUALITY (passes, evidence ledger, figure records, note substance)", n_anc_e, len(errs), n_anc_w, len(warns))):
            print(f"[{title}]")
            for w in warns[wa:wb]:
                print("  warn:", w)
            for e in errs[a:b]:
                print("  ERROR:", e)
            print(f"  -> {'OK' if b == a else str(b - a) + ' problem(s)'}")
        print("(4 HTML RENDERING AND VISUAL QA runs in `render`)")
        print("RESULT:", "OK" if not errs else f"{len(errs)} problem(s)")
    return errs, warns, man, ann


def cmd_check(a):
    errs, *_ = run_check(Path(a.dir), Path(a.annotations) if a.annotations else None, passes_path=a.passes)
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


def html_qa(ctx, path, notes, status, shot):
    """Open the finished annotated.html in a real browser and verify it. Returns (errs, warns)."""
    errs, warns, js = [], [], []
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: js.append(str(e)))
    pg.goto(Path(path).resolve().as_uri(), wait_until="load", timeout=60000)
    pg.wait_for_timeout(2000)
    info = pg.evaluate("""() => { const K = s => [...new Set([...document.querySelectorAll(s)].map(e => e.dataset.key))];
      return {drawer: !!document.getElementById('ga-drawer'), launch: !!document.getElementById('ga-launch'),
        print: !!document.getElementById('ga-print'), badges: K('.ga-badge'), cards: K('.ga-card'), boxes: K('.ga-box'),
        broken: [...document.images].filter(i => i.complete && i.naturalWidth === 0).length, imgs: document.images.length,
        external: document.querySelectorAll('img[src^=http],link[href^=http],script[src^=http]').length,
        hscroll: document.documentElement.scrollWidth > window.innerWidth + 4}; }""")
    missed = set(status.get("missed") or [])
    want = {n["key"] for n in notes} - {m if isinstance(m, str) else m.get("key") for m in missed}
    want_fig = {n["key"] for n in notes if n.get("figure") and n.get("box") and n["key"] in want}
    if not info["drawer"] or not info["launch"]:
        errs.append("annotation drawer/launcher not present in annotated.html")
    if not info["print"]:
        errs.append("printable reading-notes section missing")
    if set(info["badges"]) != want:
        errs.append(f"badges {len(info['badges'])} != anchored notes {len(want)} (missing: {sorted(want - set(info['badges']))})")
    if set(info["cards"]) != want:
        errs.append(f"drawer cards {len(info['cards'])} != anchored notes {len(want)}")
    if want_fig - set(info["boxes"]):
        errs.append(f"figure boxes missing for {sorted(want_fig - set(info['boxes']))}")
    if js:
        errs.append(f"{len(js)} JavaScript error(s): {js[0][:120]}")
    if info["broken"]:
        warns.append(f"{info['broken']}/{info['imgs']} images did not load (offline? remote hosts)")
    if info["external"]:
        warns.append(f"{info['external']} external http(s) references: those parts need internet to display")
    if info["hscroll"]:
        warns.append("page scrolls sideways at the QA viewport (layout may be clipped)")
    try:
        pg.click("#ga-launch", timeout=3000)
        pg.wait_for_timeout(400)
        hi = any(n.get("pri") == "high" for n in notes)
        if hi and "needs attention first" not in pg.inner_text("#ga-drawer").lower():
            errs.append("high-priority section missing from the drawer")
    except Exception as ex:
        errs.append(f"could not open the drawer: {ex}")
    pg.screenshot(path=str(shot))
    pg.close()
    print("[4 HTML RENDERING AND VISUAL QA]")
    print(f"  drawer={'yes' if info['drawer'] else 'NO'} badges={len(info['badges'])}/{len(want)} cards={len(info['cards'])}/{len(want)} "
          f"figure boxes={len(info['boxes'])}/{len(want_fig)} broken images={info['broken']}/{info['imgs']} js errors={len(js)}")
    for w in warns:
        print("  warn:", w)
    for e in errs:
        print("  ERROR:", e)
    print(f"  screenshot: {shot}  <- VIEW IT before delivering; an unseen page has not passed visual QA")
    print(f"  -> {'OK (automated checks)' if not errs else str(len(errs)) + ' problem(s)'}")
    return errs, warns


TYPE_COLORS = {"CONCERN": "#e5484d", "VERIFY": "#f5a524", "SPECULATION": "#8e4ec6", "NOTE": "#3e63dd", "CHECKED": "#12a594", "STRENGTH": "#30a46c"}


def build_payload(d, man, ann):
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
    return WA, notes


def boot_snippet(WA, wait_ms=400):
    wa_json = json.dumps(WA, ensure_ascii=False).replace("</", "<\\/")
    return ("<script>window.__WA__=%s;</script><script>%s</script><script>%s</script>"
            "<script>(function(){var n=0,iv=setInterval(function(){n++;"
            "if(document.readyState==='complete'||n>20){clearInterval(iv);window.__WA_START__();}},%d);})();</script>"
            % (wa_json, read_js("common.js"), read_js("overlay.js"), wait_ms))


def structural_qa(html_text, WA, man, check_anchors):
    """Browser-free checks on the finished annotated.html. Returns (errs, warns, facts). It parses and inspects the file;
    it does NOT lay the page out, so it can never stand in for browser visual QA."""
    errs, warns, facts = [], [], {}
    tree = SE.parse(html_text)
    allnodes = list(tree.iter())
    scripts = [n for n in allnodes if n.tag == "script"]
    texts = ["".join(c for c in n.children if isinstance(c, str)) for n in scripts]
    payload = [t for t in texts if t.lstrip().startswith("window.__WA__=")]
    if len(payload) != 1:
        errs.append(f"expected exactly one annotation payload script, found {len(payload)}")
    else:
        try:
            got = json.loads(payload[0].strip()[len("window.__WA__="):].rstrip(";"))
            want = {n["key"] for n in WA["notes"]}
            have = {n["key"] for n in got["notes"]}
            if want != have:
                errs.append(f"payload notes differ from annotations.json (missing {sorted(want - have)})")
            facts["payload_notes"] = len(have)
        except Exception as e:
            errs.append(f"annotation payload is not valid JSON: {e}")
    for nm in ("common.js", "overlay.js"):
        if not any(t.strip() == read_js(nm).strip() for t in texts):
            errs.append(f"shared runtime {nm} missing or modified in the output")
    foreign = [t for t in texts if t not in payload and t.strip() not in (read_js("common.js").strip(), read_js("overlay.js").strip())
               and "__WA_START__" not in t]
    if foreign:
        warns.append(f"{len(foreign)} page script(s) still present (they can rewrite the DOM and wipe the overlay)")
    node = shutil.which("node")
    if node:
        import tempfile
        for i, t in enumerate(texts):
            if t.strip() and ("__WA" in t or "ga-" in t):
                with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf:
                    tf.write(t)
                r = subprocess.run([node, "--check", tf.name], capture_output=True, text=True)
                if r.returncode:
                    errs.append(f"injected script #{i} has a JavaScript syntax error: {r.stderr.strip().splitlines()[-1][:120] if r.stderr.strip() else ''}")
        facts["js_syntax_checked"] = True
    else:
        warns.append("node not available: injected JavaScript syntax was not checked")
        facts["js_syntax_checked"] = False
    byid = {}
    for n in allnodes:
        if "data-wa-id" in n.attrs:
            byid.setdefault(n.attrs["data-wa-id"], []).append(n)
    fig_notes = [n for n in WA["notes"] if n.get("figure")]
    for n in fig_notes:
        els = byid.get(n["figure"], [])
        if len(els) != 1:
            errs.append(f"{n['key']}: figure {n['figure']} maps to {len(els)} elements in the output (need exactly 1)")
    facts["figure_boxes_expected"] = len(fig_notes)
    facts["figures_tagged"] = len(byid)
    for fid, els in byid.items():
        el = els[0]
        if el.tag == "img":
            src = el.attrs.get("src", "")
            if not src:
                warns.append(f"{fid}: <img> has no src")
            elif not (src.startswith("data:") or re.match(r"^https?://", src)):
                warns.append(f"{fid}: local image {src[:50]!r} was not inlined; it will not load from the single annotated file")
            elif src.startswith("http"):
                warns.append(f"{fid}: remote image {src[:50]!r} needs internet when the page is opened")
    refs = []
    for n in allnodes:
        if n.tag in ("img", "source", "video", "audio", "track", "embed"):
            for at in ("src", "srcset", "poster"):
                v = (n.attrs.get(at) or "").strip()
                if v and not re.match(r"^(data:|https?:|//|#|blob:)", v):
                    refs.append(f"<{n.tag} {at}={v[:40]!r}>")
    if refs:
        warns.append(f"{len(refs)} relative media reference(s) not inlined, they will not load from the single file: {refs[0]}")
    left = [n.attrs.get("href") for n in allnodes if n.tag == "link" and "stylesheet" in (n.attrs.get("rel") or "").lower()
            and not re.match(r"^(https?:)?//|^data:", n.attrs.get("href") or "")]
    if left:
        warns.append(f"{len(left)} local stylesheet(s) not inlined: {left[0][:50]}")
    if check_anchors:
        body = next((n for n in allnodes if n.tag == "body"), tree)
        art = SE.pick_root(body)
        blocks = [SE.text_of(e) for e in art.iter() if e.tag in SE.BLOCK and not SE._has_block_desc(e) and not SE._skipped(e)]
        blocks = [b for b in blocks if b]
        facts["paragraphs_in_output"] = len(blocks)
        if len(blocks) != len(man["paragraphs"]):
            warns.append(f"output has {len(blocks)} text blocks, the bundle has {len(man['paragraphs'])}: anchors may land differently")
        text_notes = [n for n in WA["notes"] if not n.get("figure")]
        miss = [n["key"] for n in text_notes if not any(" ".join(n["quote"].split()) in b for b in blocks)]
        if miss:
            errs.append(f"text anchors not found in the output document: {miss}")
        facts["text_anchors_verified"] = len(text_notes) - len(miss)
        facts["text_anchors_expected"] = len(text_notes)
    return errs, warns, facts


def figure_previews(d, man, ann):
    """Pillow-drawn preview of every figure annotation (colored box + marker). This is a visual aid for the agent to look at,
    produced without a browser. It shows WHERE the normalised boxes fall on the figure image; it is not a page render."""
    from PIL import Image, ImageDraw, ImageFont
    figs = {f["id"]: f for f in man["figures"]}
    qd = d / "qa_figures"
    shutil.rmtree(qd, ignore_errors=True)
    qd.mkdir()
    per = {}
    for n in ann["notes"]:
        if n.get("figure"):
            per.setdefault((n["figure"], n.get("frame")), []).append(n)
    outs = []
    for (fid, fr), ns in per.items():
        f = figs.get(fid, {})
        file = next((x["file"] for x in f.get("frames", []) if x["i"] == fr), None) if fr else f.get("file")
        if not file:
            continue
        im = Image.open(d / file).convert("RGB")
        W, H = im.size
        dr = ImageDraw.Draw(im, "RGBA")
        try:
            font = ImageFont.load_default(size=max(12, W // 45))
        except TypeError:
            font = ImageFont.load_default()
        for n in ns:
            col = TYPE_COLORS.get(n["type"], "#3e63dd")
            rgb = tuple(int(col[i:i + 2], 16) for i in (1, 3, 5))
            b = n.get("box") or [0, 0, 1, 1]
            x0, y0, x1, y1 = b[0] * W, b[1] * H, (b[0] + b[2]) * W, (b[1] + b[3]) * H
            dr.rectangle([x0, y0, x1, y1], fill=rgb + (36,), outline=rgb + (255,), width=max(2, W // 300))
            lab = f"{n['key']} · {n['type']}" + ("" if n.get("box") else " (whole figure)")
            tw = dr.textlength(lab, font=font)
            dr.rectangle([x0, y0, x0 + tw + 8, y0 + font.size + 6 if hasattr(font, "size") else y0 + 20], fill=rgb + (255,))
            dr.text((x0 + 4, y0 + 2), lab, fill=(255, 255, 255, 255), font=font)
        p = qd / (f"{fid}.png" if not fr else f"{fid}.frame{fr:02d}.png")
        im.save(p)
        outs.append(p)
    if outs:
        thumbs = []
        for p in outs:
            t = Image.open(p)
            t.thumbnail((520, 400))
            thumbs.append(t)
        cols = min(3, len(thumbs))
        rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 530, rows * 410), "white")
        for i, t in enumerate(thumbs):
            sheet.paste(t, ((i % cols) * 530 + 5, (i // cols) * 410 + 5))
        sheet.save(d / "qa_figures.png")
    return outs


def qa_report(d, engine, man, ann, s_errs, s_warns, facts, browser):
    """Print + save the three separate QA statuses. browser = None (not run) or (errs, warns, screenshot)."""
    figs = man["figures"]
    cov = ann.get("coverage", {})
    have = [f["id"] for f in figs if f.get("file") and "did not load" not in (f.get("error") or "")]
    unavailable = [f["id"] for f in figs if f["id"] not in have]
    status = {
        "engine": engine,
        "visual_inspection": {
            "figures_total": len(figs), "figures_with_image": len(have), "declared_viewed": sorted(set(cov.get("figures_viewed", [])) & set(have)),
            "unavailable_or_not_viewable": unavailable,
            "note": "declared_viewed comes from coverage in annotations.json and passes.json; no script can verify that the images were actually looked at",
            "figure_preview_sheet": "qa_figures.png" if (d / "qa_figures.png").exists() else None},
        "static_structural_qa": {"result": "PASS" if not s_errs else "FAIL", "errors": s_errs, "warnings": s_warns, "facts": facts},
        "browser_visual_qa": ({"result": "NOT RUN", "reason": "no browser opened the output; layout, drawer and box positions were not rendered by a real browser"}
                              if browser is None else {"result": "PASS" if not browser[0] else "FAIL", "errors": browser[0], "warnings": browser[1],
                                                       "screenshot": str(Path(browser[2]).name)}),
    }
    (d / "qa_status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False), encoding="utf-8")
    print("[4 RENDERING QA: three separate statuses]")
    vi = status["visual_inspection"]
    print(f"  visual_inspection: {vi['figures_with_image']}/{vi['figures_total']} figures have an image; {len(vi['declared_viewed'])} declared viewed"
          + (f"; NOT viewable: {unavailable}" if unavailable else "") + ("; previews: qa_figures.png (view it)" if vi["figure_preview_sheet"] else ""))
    sq = status["static_structural_qa"]
    print(f"  static_structural_qa: {sq['result']}  {facts}")
    for w in s_warns:
        print("    warn:", w)
    for e in s_errs:
        print("    ERROR:", e)
    bq = status["browser_visual_qa"]
    print(f"  browser_visual_qa: {bq['result']}" + (f" ({bq['reason']})" if bq["result"] == "NOT RUN" else f"  screenshot={bq['screenshot']}  <- VIEW it before delivering"))
    if browser is not None:
        for w in browser[1]:
            print("    warn:", w)
        for e in browser[0]:
            print("    ERROR:", e)
    if bq["result"] == "NOT RUN":
        print("  REPORT TO THE USER: static structural QA " + ("passed" if not s_errs else "FAILED") + "; browser visual QA was NOT run.")
    return status


def cmd_render(a):
    d = Path(a.dir)
    errs, warns, man, ann = run_check(d, Path(a.annotations) if a.annotations else None, quiet=True, passes_path=a.passes)
    if errs and not a.force:
        print("check failed, fix these first (or pass --force):")
        for e in errs:
            print("  ERROR:", e)
        return 1
    eng = man.get("engine", "browser")
    if getattr(a, "engine", "auto") == "static" and eng != "static":
        raise SystemExit("this bundle was fetched with the browser engine; re-run `fetch --engine static`")
    if eng == "static":
        return render_static(a, d, man, ann)
    ok, cat, detail = browser_status()
    if not ok:
        raise SystemExit(f"bundle was fetched with the browser engine but the browser is unavailable ({cat}: {detail}). "
                         "Re-run `fetch --engine static` on the saved page to use the browserless engine.")
    return render_browser(a, d, man, ann)


def render_static(a, d, man, ann):
    if getattr(a, "only", None) == "pdf":
        raise SystemExit("annotated.pdf needs a browser; the static engine writes annotated.html only (HTML in -> HTML out)")
    info = man["static"]
    html_path, root = d / info["html"], d / info["root"]
    raw = html_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != info["sha256"]:
        raise SystemExit("source page in the bundle changed since fetch; fetch again")
    src_html = raw.decode("utf-8", "replace")
    enc = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw[:4096], re.I)
    if enc and enc.group(1).lower() not in (b"utf-8", b"utf8"):
        try:
            src_html = raw.decode(enc.group(1).decode())
        except Exception:
            pass
    inject, lost = SE.inject_for(src_html, man["figures"])
    if lost:
        raise SystemExit(f"could not re-locate figure elements in the source page: {lost}")
    WA, notes = build_payload(d, man, ann)
    html = SE.build_html(src_html, inject, html_path.parent, man["url"], boot_snippet(WA), root)
    (d / "annotated.html").write_text(html, encoding="utf-8")
    s_errs, s_warns, facts = structural_qa(html, WA, man, check_anchors=True)
    figure_previews(d, man, ann)
    qa_report(d, "static", man, ann, s_errs, s_warns, facts, None)
    print(f"notes: {len(notes)}  text anchors verified {facts.get('text_anchors_verified', 0)}/{facts.get('text_anchors_expected', 0)}  "
          f"figure boxes expected {facts.get('figure_boxes_expected', 0)}")
    print("wrote: annotated.html   (QA side files, not deliverables: qa_status.json, qa_figures.png)")
    return 3 if s_errs else 0


def render_browser(a, d, man, ann):
    from playwright.sync_api import sync_playwright

    WA, notes = build_payload(d, man, ann)
    wa_json = json.dumps(WA, ensure_ascii=False).replace("</", "<\\/")
    common, overlay = read_js("common.js"), read_js("overlay.js")

    with sync_playwright() as p:
        lo, co = browser_opts(a)
        br = launch(p, **lo)
        ctx = br.new_context(viewport={"width": a.width, "height": a.height}, **co)
        page = ctx.new_page()
        load_page(page, man["url"], a.wait)
        page.evaluate(read_js("extract.js"))
        tagged = page.evaluate("window.__WA_EXTRACT__().figures.length")
        if tagged != len(man["figures"]):
            print(f"WARNING: page now has {tagged} figures, the bundle has {len(man['figures'])}: the page changed since fetch; figure notes may attach to the wrong media")

        # 1) static HTML snapshot (scripts removed so the site cannot wipe the overlay; overlay runs on open)
        html = page.content()
        html = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.S | re.I)
        html = re.sub(r"(<head[^>]*>)", r'\1<base href="%s">' % man["url"], html, count=1, flags=re.I)
        boot = boot_snippet(WA)
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
        qa_errs = []
        bq = None
        if only != "pdf" and (d / "annotated.html").exists():
            qa_errs, qa_warns = html_qa(ctx, d / "annotated.html", notes, status, d / "qa_html.png")
            bq = (qa_errs, qa_warns, d / "qa_html.png")
        else:
            print("[4 HTML RENDERING AND VISUAL QA] skipped (no annotated.html in this run)")
        br.close()

    if bq is not None:
        s_errs, s_warns, facts = structural_qa((d / "annotated.html").read_text(encoding="utf-8"), WA, man, check_anchors=False)
        figure_previews(d, man, ann)
        qa_report(d, "browser", man, ann, s_errs, s_warns, facts, bq)
        qa_errs = qa_errs + s_errs

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
    return 3 if qa_errs else (0 if not status["missed"] else 2)


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
    f.add_argument("--engine", choices=["auto", "browser", "static"], default="auto",
                   help="auto: Chromium if it launches, else the browserless engine for saved pages")
    f.set_defaults(fn=cmd_fetch)
    c = sub.add_parser("check", help="verify coverage + anchors in annotations.json")
    c.add_argument("dir")
    c.add_argument("--annotations")
    c.add_argument("--passes", help="three-pass record (default <dir>/passes.json)")
    c.set_defaults(fn=cmd_check)
    r = sub.add_parser("render", help="write annotated.pdf / annotated.html / annotated.user.js")
    r.add_argument("dir")
    r.add_argument("--annotations")
    r.add_argument("--passes", help="three-pass record (default <dir>/passes.json)")
    r.add_argument("--wait", type=float, default=2.0)
    r.add_argument("--width", type=int, default=1100)
    r.add_argument("--height", type=int, default=900)
    r.add_argument("--only", choices=["html", "pdf"], help="write just that file (html: annotated.html only; pdf: annotated.pdf only); default writes all three")
    r.add_argument("--force", action="store_true", help="render even if check reports problems")
    r.add_argument("--insecure-tls", action="store_true")
    r.add_argument("--no-proxy", action="store_true")
    r.add_argument("--engine", choices=["auto", "static"], default="auto", help="static: require the browserless renderer")
    r.set_defaults(fn=cmd_render)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
