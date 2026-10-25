#!/usr/bin/env bash
# Turn-key: Markdown -> PDF + DOCX for one or more .md files.
# PDFs/DOCX are written next to each source .md. Title = filename without extension.
#
# Usage (run from the repo root):
#   .claude/skills/docgen/scripts/docgen.sh [--pdf-only|--docx-only] <file1.md> [file2.md ...]
#
# Notes:
# - Chromium is auto-detected (md2pdf.cjs); no NODE_PATH / no hard-coded build.
# - LibreOffice gets a FRESH profile per run (-env:UserInstallation) — a 2nd
#   soffice call in a session otherwise crashes with DeploymentException.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="both"
case "${1:-}" in
  --pdf-only)  MODE="pdf";  shift ;;
  --docx-only) MODE="docx"; shift ;;
esac
[ "$#" -ge 1 ] || { echo "Usage: docgen.sh [--pdf-only|--docx-only] <file.md> [...]"; exit 1; }

TMP="$(mktemp -d /tmp/nkensa_docgen.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

for md in "$@"; do
  [ -f "$md" ] || { echo "skip (not found): $md"; continue; }
  dir="$(dirname "$md")"; base="$(basename "$md" .md)"; title="$base"
  if [ "$MODE" != "docx" ]; then
    node "$SCRIPT_DIR/md2pdf.cjs" "$md" "$dir/$base.pdf" "$title"
  fi
  if [ "$MODE" != "pdf" ]; then
    node "$SCRIPT_DIR/md2html.cjs" "$md" "$TMP/$base.html" "$title"
  fi
done

if [ "$MODE" != "pdf" ]; then
  # One soffice call, fresh profile, all HTML at once.
  prof="$TMP/loprofile"
  soffice -env:UserInstallation="file://$prof" --headless \
    --convert-to "docx:MS Word 2007 XML" --outdir "$TMP" "$TMP"/*.html >/dev/null 2>&1 || true
  # Move each produced docx next to its source .md.
  for md in "$@"; do
    [ -f "$md" ] || continue
    dir="$(dirname "$md")"; base="$(basename "$md" .md)"
    if [ -f "$TMP/$base.docx" ]; then
      cp "$TMP/$base.docx" "$dir/$base.docx"
      echo "DOCX written: $dir/$base.docx"
    else
      echo "WARN: docx not produced for $base (check LibreOffice)"
    fi
  done
fi
