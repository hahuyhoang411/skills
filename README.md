# Skills

Agent skills by [hahuyhoang411](https://github.com/hahuyhoang411): small, practical, and built to be hacked on.

Skills are plain folders of instructions and scripts that an AI agent loads when the task fits. No framework, no lock-in, no 40-page onboarding. They work in Claude, ChatGPT, Claude Code, Codex and any agent that reads the Agent Skills format. Use them as they are, or open `SKILL.md` and make them yours.

## Installation (2-minute setup)

Grab the latest bundle: **[annotator.zip](https://github.com/hahuyhoang411/skills/raw/main/dist/annotator.zip)**. Then pick your platform.

### Claude (claude.ai, Desktop, mobile)

1. Go to **Plugins → Add → Upload plugin** and choose the `.zip`.
2. Open a **new session** and type `/your-installed-plugin`, e.g. `/annotator`.

### ChatGPT

1. Go to **Plugins → Add → Upload plugin archive** and choose the `.zip` (needs a plan with Plugins).
2. Start a new chat and type `@annotator` (or `@` plus whatever plugin you installed).

### Claude Code

```
/plugin marketplace add hahuyhoang411/skills
/plugin install annotator@hahuyhoang411-skills
```

### Codex, Cursor, and other agents

```
npx skills add hahuyhoang411/skills
```

Node.js required. The installer lets you pick which skills to take.

### By hand

Copy a folder from `skills/` (e.g. `skills/annotator/`) into your agent's skills directory. That's all a skill is.

## Updating

Every release raises `version` (currently **0.2.0**). Old installs keep running the cached version until it changes, so yes, you do have to update.

- **Claude:** upload the new `.zip` again.
- **ChatGPT:** open the plugin → Upload new version → choose the new `.zip`.
- **Claude Code:** `/plugin marketplace update hahuyhoang411-skills`, then `/plugin update annotator@hahuyhoang411-skills`, then restart the session.
- **npx:** rerun `npx skills add hahuyhoang411/skills`.

## Why these skills exist

Agents are great at doing what you said and occasionally terrible at doing what you meant. These skills exist to close that gap for the boring, repeatable jobs: the ones where you'd otherwise paste the same 400-word prompt for the fifteenth time.

A few rules I try to hold to:

- **Small and readable.** Each skill is a folder you can read in one sitting. If you can't tell what it does by skimming `SKILL.md`, that's a bug.
- **Evidence over vibes.** Skills should say *why*, show their work, and flag what they didn't check.
- **Works anywhere.** One skill, many agents. Platform quirks go in the skill's own README, not in your head.
- **Yours to edit.** Fork it, trim it, rewrite the prompts. Nothing here is sacred.

## Reference

### Research and reading

- **[annotator](skills/annotator/README.md)**: Read a PDF or a saved web page with Keshav's three-pass method and get back one color-coded, figure-aware annotated copy. PDF in → PDF out; HTML in → HTML out.

More skills will land here as I build and battle-test them. Each gets its own folder under `skills/` and a row in this list.

## Maintainers

- **Layout:** each skill lives in `skills/<name>/` with a `SKILL.md` and its own `README.md`.
- **Build:** `sh scripts/build.sh` checks versions and front matter, then rebuilds `dist/annotator.zip` (hybrid: skill layout + plugin layout). Commit `dist/`.
- **Release:** set the same `version` in `plugin.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` and the `.claude-plugin/marketplace.json` entry; build; push.
- **Tests:** `python tests/run_tests.py` (needs pymupdf, pillow, pyyaml; Chromium optional).

## License

[MIT](LICENSE)
