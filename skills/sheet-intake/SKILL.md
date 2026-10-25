---
name: sheet-intake
description: Alias of the freetext-to-spreadsheet skill — same engine, shorter name. Use only when the user types /sheet-intake or says "sheet intake"; then read and follow ~/.qwen/skills/freetext-to-spreadsheet/SKILL.md exactly (profiles, --dry-run first, report the preview and warnings).
---

# Sheet intake (alias)

This is only a shorter name for **`/freetext-to-spreadsheet`**. Do not duplicate its logic here.

1. Read `~/.qwen/skills/freetext-to-spreadsheet/SKILL.md` and follow it exactly.
2. Run the engine: `python3 ~/.qwen/skills/freetext-to-spreadsheet/scripts/intake.py --list-profiles` to see what can be logged, then `--profile <name> --dry-run ...` before any real write.

Keep this file minimal: any change to behaviour goes in the main skill, never here.
