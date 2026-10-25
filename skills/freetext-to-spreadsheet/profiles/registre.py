"""
Profile: registre — personal + JM financial transactions and life events, into "Registre" (via the "Import Registre" tab and
its Apps Script trigger). Free text ("j'ai dépensé 5000 au marché", a voice-note transcript) -> DSL -> Import Registre.
Rules (Compte defaults to Cash, Heure to now, Orange Money fee tags, never invent Poste/amount) live in the DSL prompt:
_freetext-import-lib/append_import.py TARGETS['registre'] — single source of truth, not copied here.
Dedicated skill: freetext-to-registre.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _import_trigger import ImportTriggerProfile  # noqa: E402


class Registre(ImportTriggerProfile):
    name = 'registre'
    description = 'Finance/life transactions and events -> "Registre" (through the "Import Registre" tab + trigger)'
    import_tab = 'Import Registre'
    target_key = 'registre'


PROFILE = Registre()
