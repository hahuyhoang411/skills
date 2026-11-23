#!/bin/sh
# Rebuild dist/annotator.zip. Run from repo root: sh scripts/build.sh
set -e
rm -rf dist && mkdir dist
find skills -name __pycache__ -prune -exec rm -rf {} +
(cd skills && zip -qr ../dist/annotator.zip annotator)
echo "built dist/annotator.zip"
