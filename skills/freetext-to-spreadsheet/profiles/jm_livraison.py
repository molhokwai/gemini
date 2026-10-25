"""
Profile: jm-livraison — JM cake/ice-cream deliveries, sales and collections at points, into "Dépôt / vente" (via the "Import"
tab and its Apps Script trigger, which resolves Nr/Nom against "Points de dépôt / vente"). Free text -> DSL -> Import.
The DSL prompt lives in _freetext-import-lib/append_import.py TARGETS['jm'] — single source of truth, not copied here.
Dedicated skill: freetext-to-jm-livraison-collecte.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _import_trigger import ImportTriggerProfile  # noqa: E402


class JmLivraison(ImportTriggerProfile):
    name = 'jm-livraison'
    description = 'JM delivery/sale/collection at a point -> "Dépôt / vente" (through the "Import" tab + trigger)'
    import_tab = 'Import'
    target_key = 'jm'


PROFILE = JmLivraison()
