# Host adapter

Only file access, script staging and delivery differ by host. Method, schemas, gates, overlay are identical.

## ChatGPT
- Plugin files may not be mounted. Stage every file the route needs, same relative paths, from the installed skill resources (`skills://plugins/annotator/annotator/...`) into `WORK/annotator/`:
  - all: `scripts/preflight.py`, `scripts/gates.py`
  - web: `scripts/web/webannotate.py`, `scripts/web/static_engine.py`, `scripts/web/js/{common,extract,overlay}.js`
  - PDF: `scripts/pdf/extract_pdf.py`, `scripts/pdf/annotate_pdf.py`
  - references/assets you read
  Never reconstruct a script from excerpts; never stop after a failed path search.
- Attachment: `/mnt/data` or the path returned by the file tools.
- Browser: Python Playwright with system Chromium/Chrome (auto-discovered: `ANNOTATOR_CHROMIUM_PATH`, `PLAYWRIGHT_CHROMIUM_EXECUTABLE`, `PATH`, standard install paths, then Playwright's managed browser). No `playwright-cli`, npm wrapper, remote browser or extra account.
- No internet by default: live URLs need a saved page or PDF instead.
- Deliver: save to `/mnt/data`, `ls -l` the file, link that path.

## Claude / Claude Desktop
- `UPLOADS=/mnt/user-data/uploads`, `OUT=/mnt/user-data/outputs`; present the file with the host's file-delivery tool.
- Blocked live host: allow it under Settings > Capabilities > Domain allowlist, or ask for a saved page/PDF.

## Claude Code / local
Read-only inputs, dedicated output dir, print the output path.

## Rules
- Saved HTML: browser engine if Chromium launches, else static engine (`--engine static`). Decide from the current launch result only.
- Live URL: browser + successful navigation required.
- Static engine: no page JS, no CSS layout, no canvas/iframe/video capture, no PDF output; unavailable figures are declared.
- Install only what `preflight` lists as missing.
