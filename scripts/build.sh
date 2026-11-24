#!/bin/sh
# Build dist/annotator.zip (hybrid: skill layout at root + plugin layout under skills/). Run from repo root.
set -e
python3 - <<'PY'
import json, re, sys
v = {f: json.load(open(f))["version"] for f in ("plugin.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json")}
v[".claude-plugin/marketplace.json"] = json.load(open(".claude-plugin/marketplace.json"))["plugins"][0].get("version")
if len(set(v.values())) != 1:
    sys.exit(f"version mismatch: {v}")
fm = re.match(r"^---\n(.*?)\n---\n", open("skills/annotator/SKILL.md").read(), re.S).group(1)
try:
    import yaml; d = yaml.safe_load(fm); assert d["name"] and d["description"]
except ImportError:
    bad = [l for l in fm.splitlines() if l.partition(":")[2].strip()[:1] not in ("", '"', "'", "|", ">") and ": " in l.partition(":")[2]]
    assert not bad, f"unquoted ': ' in front matter (invalid YAML on ChatGPT): {bad}"
print("version", set(v.values()).pop(), "| front matter ok")
PY
rm -rf dist /tmp/annotator-build && mkdir -p dist /tmp/annotator-build/annotator
find skills -name __pycache__ -prune -exec rm -rf {} +
B=/tmp/annotator-build/annotator
cp -R skills/annotator/. "$B"/
mkdir -p "$B/skills" "$B/.codex-plugin" "$B/.claude-plugin"
cp -R skills/annotator "$B/skills/annotator"
cp plugin.json "$B"/
cp .codex-plugin/plugin.json "$B/.codex-plugin/"
cp .claude-plugin/plugin.json "$B/.claude-plugin/"
(cd /tmp/annotator-build && zip -qr "$OLDPWD/dist/annotator.zip" annotator)
echo "built dist/annotator.zip"
