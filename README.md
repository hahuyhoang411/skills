# skills

Agent Skills by hahuyhoang411.

| Skill | What it does |
| --- | --- |
| [annotator](skills/annotator/README.md) | Read a PDF or saved web page (Keshav three-pass) and return one color-coded, figure-aware annotated copy. PDF in → PDF out; HTML in → HTML out. |

## Install

Download **[annotator.zip](https://github.com/hahuyhoang411/skills/raw/main/dist/annotator.zip)**.

- **ChatGPT:** Plugins → Add → Upload plugin archive → choose `annotator.zip`. New chat, attach a PDF or saved page, type `@annotator annotate this`. Needs a plan with Plugins; ChatGPT has no internet by default, so give it a PDF or a saved page (see the [skill README](skills/annotator/README.md)).
- **Claude.ai / Claude Desktop:** Settings → Capabilities → Skills → Upload skill → `annotator.zip` (menu may read Customize → Skills).
- **Claude Code:**
  ```
  /plugin marketplace add hahuyhoang411/skills
  /plugin install annotator@hahuyhoang411-skills
  ```
- **Other agents (Codex, Cursor, …):** `npx skills add hahuyhoang411/skills` (Node.js required).
- **By hand:** copy `skills/annotator/` into your agent's skills folder.

## Update
Every release raises `version` (currently 0.2.0). Old installs keep running the cached version until it changes.

- **ChatGPT:** open the plugin → Upload new version → `annotator.zip`.
- **Claude.ai:** upload the new `annotator.zip` again.
- **Claude Code:** `/plugin marketplace update hahuyhoang411-skills`, then `/plugin update annotator@hahuyhoang411-skills`, then restart the session.
- **npx:** rerun `npx skills add hahuyhoang411/skills`.

## Maintainers
- Skill source: `skills/annotator/` only. `sh scripts/build.sh` checks versions and front matter, then rebuilds `dist/annotator.zip` (hybrid: skill layout + plugin layout). Commit `dist/`.
- Release: set the same `version` in `plugin.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` and the `.claude-plugin/marketplace.json` entry; build; push.
- Tests: `python tests/run_tests.py` (needs pymupdf, pillow, pyyaml; Chromium optional).

## License
[MIT](LICENSE)
