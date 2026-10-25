#!/usr/bin/env python3
"""Thin wrapper (2026-09-21): runs the shared engine with the `students-grading` profile — same flags as before
(--student --program --program-link --date --comment --csv/--csv-text --text --header --check --dry-run).
The previous standalone implementation is kept next to this file as students_grading.legacy.py (delete once trusted)."""
import os
import sys

ENGINE = os.path.expanduser('~/.qwen/skills/freetext-to-spreadsheet/scripts/intake.py')
os.execv(sys.executable, [sys.executable, ENGINE, '--profile', 'students-grading'] + sys.argv[1:])
