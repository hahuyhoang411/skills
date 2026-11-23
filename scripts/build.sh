#!/bin/sh
# Build dist/annotator.zip: ONE hybrid zip that works in both uploaders.
#   annotator/SKILL.md ...            -> skill layout (Claude.ai / ChatGPT "upload skill")
#   annotator/plugin.json + skills/   -> plugin layout (ChatGPT "New Plugin")
# Run from repo root: sh scripts/build.sh
set -e
rm -rf dist /tmp/annotator-build && mkdir -p dist /tmp/annotator-build/annotator
find skills -name __pycache__ -prune -exec rm -rf {} +
B=/tmp/annotator-build/annotator
cp -R skills/annotator/. "$B"/
mkdir -p "$B/skills" && cp -R skills/annotator "$B/skills/annotator"
cp plugin.json "$B"/
mkdir -p "$B/.codex-plugin" "$B/.claude-plugin"
cp .codex-plugin/plugin.json "$B/.codex-plugin/"
cp .claude-plugin/plugin.json "$B/.claude-plugin/"
(cd /tmp/annotator-build && zip -qr "$OLDPWD/dist/annotator.zip" annotator)
echo "built dist/annotator.zip"
