# skills

Agent Skills by hahuyhoang411.

| Skill | What it does |
| --- | --- |
| [annotator](skills/annotator/SKILL.md) | Read and annotate a PDF or web page into a color-coded reading copy (Keshav three-pass). Same format out as in: PDF in, PDF out; HTML in, HTML out. |

## Install

Download **[annotator.zip](https://github.com/hahuyhoang411/skills/raw/main/dist/annotator.zip)**, then:

- **Claude.ai / Claude Desktop:** Settings > Capabilities > Skills > Upload skill (menus may be named Customize > Skills).
- **ChatGPT:** Plugins > New plugin > Choose file > `annotator.zip` > Add plugin (or Plugins > Skills > Create > Upload). Plugins/Skills are documented for Business, Enterprise, Healthcare and Edu plans; Plus/Pro unverified.

Then start a new chat, attach a PDF or a saved web page, and say "annotate this". In ChatGPT you can type `@annotator annotate this`.

ChatGPT's sandbox has no internet: give it a saved page (.html or .zip) or a PDF, not a live URL.

### Terminal (Claude Code, Codex, Cursor and others)

```
npx skills add hahuyhoang411/skills
```

Needs Node.js. Single skill: `npx skills add hahuyhoang411/skills --skill annotator`.

### Claude Code plugin

```
/plugin marketplace add hahuyhoang411/skills
/plugin install annotator@hahuyhoang411-skills
```

Then start a new session.

### By hand

Copy `skills/annotator/` into `~/.claude/skills/` (Claude Code) or your agent's skills folder.

## Maintainers

- Add a skill: create `skills/<name>/SKILL.md`, add it to `plugins` in `.claude-plugin/marketplace.json`, add a table row above.
- After any skill change run `sh scripts/build.sh` and commit `dist/`. The zip is a hybrid (skill layout + plugin layout) so one file works in every uploader.

## License

[MIT](LICENSE)
