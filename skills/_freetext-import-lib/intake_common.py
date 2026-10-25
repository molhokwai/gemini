#!/usr/bin/env python3
"""
Shared helpers for the "sheet intake" family of skills (students-grading, and the generic skill that
will absorb freetext-to-registre / freetext-to-jm-livraison-collecte / taina-bipolar-disorder-log).

- Sheets: a tiny stdlib client (OAuth via sheets_oauth.py — same token as every other skill here).
- llm_json(): routes a prompt through provider-router (Gemini -> Groq -> DeepSeek -> Cerebras, per the
  'other' chain), returns parsed JSON. Never invents data: callers put that rule in the system prompt.

Stdlib only. Imports append_import for its .env.local loading and provider plumbing (same directory).
"""
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import append_import as ai  # noqa: E402  (loads .env.local, exposes _route_provider/_call_llm/_mark_provider_failed)
from sheets_oauth import get_access_token  # noqa: E402

SPREADSHEET_ID = ai.SPREADSHEET_ID   # "Registre Financier — life/"
BASE = f'https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}'


class Sheets:
    def __init__(self, spreadsheet_id=SPREADSHEET_ID):
        self.base = f'https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}'
        self.tok = get_access_token()

    def call(self, method, url, body=None):
        req = urllib.request.Request(
            url, method=method, data=json.dumps(body).encode('utf-8') if body is not None else None,
            headers={'Authorization': 'Bearer ' + self.tok, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise SystemExit(f'Sheets API {e.code}: {e.read().decode("utf-8", "replace")[:600]}')

    def meta(self, fields='sheets.properties'):
        return self.call('GET', f'{self.base}?fields={urllib.parse.quote(fields)}')

    def sheet_id(self, title):
        for s in self.meta()['sheets']:
            if s['properties']['title'] == title:
                return s['properties']['sheetId']
        return None

    def batch(self, requests, chunk=400):
        out = []
        for i in range(0, len(requests), chunk):
            out.append(self.call('POST', f'{self.base}:batchUpdate', {'requests': requests[i:i + chunk]}))
        return out

    def get_values(self, a1, render='FORMATTED_VALUE'):
        url = f'{self.base}/values/{urllib.parse.quote(a1, safe="")}?valueRenderOption={render}'
        return self.call('GET', url).get('values', [])

    def put_values(self, a1, rows, input_option='USER_ENTERED'):
        url = f'{self.base}/values/{urllib.parse.quote(a1, safe="")}?valueInputOption={input_option}'
        return self.call('PUT', url, {'range': a1, 'majorDimension': 'ROWS', 'values': rows})

    def append_values(self, a1, rows, input_option='USER_ENTERED'):
        url = (f'{self.base}/values/{urllib.parse.quote(a1, safe="")}:append?valueInputOption={input_option}'
               '&insertDataOption=INSERT_ROWS')
        return self.call('POST', url, {'majorDimension': 'ROWS', 'values': rows})


def _parse_json_loose(text):
    t = text.strip()
    t = re.sub(r'^```(?:json)?\s*', '', t)
    t = re.sub(r'\s*```$', '', t)
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r'(\{.*\}|\[.*\])', t, re.S)
        if m:
            return json.loads(m.group(1))
        raise


def llm_json(system_prompt, user_text):
    """Tries each provider in the 'other' chain until one answers with parseable JSON."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        state_path = f.name
    try:
        json.dump({'failed': {}}, open(state_path, 'w'))
        last_error = None
        for _ in range(4):
            cfg = ai._route_provider(state_path)
            key = os.environ.get(cfg['api_key_env'])
            try:
                raw = ai._call_llm(cfg['base_url'], cfg['model'], key, system_prompt, user_text)
                return _parse_json_loose(raw)
            except (urllib.error.HTTPError, urllib.error.URLError) as e:
                last_error = f'{cfg["provider"]}: {e}'
                ai._mark_provider_failed(cfg['provider'], state_path, str(e))
            except (json.JSONDecodeError, ValueError) as e:
                last_error = f'{cfg["provider"]}: unparseable JSON ({e})'
                ai._mark_provider_failed(cfg['provider'], state_path, 'bad json')
        raise SystemExit(f'All LLM providers failed. Last error: {last_error}')
    finally:
        os.unlink(state_path)
