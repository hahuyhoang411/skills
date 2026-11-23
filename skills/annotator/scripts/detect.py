#!/usr/bin/env python3
"""Decide the route for an input. Prints one word: pdf | web | saved-page | unknown  (plus a hint line).

  python detect.py <path-or-url>

- local file whose first bytes are %PDF            -> pdf
- local .html/.htm/.zip/.mhtml (saved web page)    -> saved-page   (web route, offline)
- URL ending in .pdf or /pdf/ (e.g. arxiv)         -> pdf-url      (download first, then pdf route)
- any other http(s) URL                            -> web
"""
import sys, re
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: detect.py <path-or-url>")
    a = sys.argv[1]
    if re.match(r"^https?://", a):
        path = re.sub(r"[?#].*$", "", a).lower()
        if path.endswith(".pdf") or "/pdf/" in path:
            print("pdf-url\nhint: download to ./input.pdf if the host is reachable (doctor), else ask the user to upload the PDF")
        else:
            print("web\nhint: run scripts/web/webannotate.py doctor <url> first")
        return
    p = Path(a).expanduser()
    if not p.exists():
        print("unknown\nhint: file not found; check the upload dir (/mnt/user-data/uploads or /mnt/data)")
        return
    head = p.read_bytes()[:1024]
    if head.lstrip()[:5] == b"%PDF-" or b"%PDF-" in head[:1024]:
        print("pdf")
    elif p.suffix.lower() in (".html", ".htm", ".zip", ".mhtml", ".mht"):
        print("saved-page\nhint: web route works offline on a saved page (.mhtml: ask for .html/.zip or a PDF print instead)" if p.suffix.lower() in (".mhtml", ".mht") else "saved-page")
    else:
        print("unknown\nhint: not a PDF or saved web page")


if __name__ == "__main__":
    main()
