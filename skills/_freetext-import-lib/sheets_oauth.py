#!/usr/bin/env python3
"""
Minimal, dependency-free Google OAuth2 "installed application" flow for Sheets API access, tied
to the user's own Google account (mayou.nkensa@gmail.com) — no service account. Stdlib only
(urllib, http.server): works without pip installs, since neither `requests` nor
`google-auth-oauthlib` are available in every environment this might run from.

One-time setup (see README.md in this directory for the full Google Cloud Console steps):
  1. Create an OAuth Client ID (Desktop app type), download client_secret.json.
  2. Save it at CLIENT_SECRET_PATH below — NEVER commit this file to git.
  3. Run: python3 sheets_oauth.py --authorize
     Opens a URL to visit once; after granting access, a token is cached at TOKEN_PATH for all
     future non-interactive use (auto-refreshed via the cached refresh_token).
"""
import argparse
import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

SECRETS_DIR = os.path.expanduser('~/.claude-nkensa/secrets/freetext-import')
CLIENT_SECRET_PATH = os.path.join(SECRETS_DIR, 'client_secret.json')
TOKEN_PATH = os.path.join(SECRETS_DIR, 'sheets_token.json')
SCOPE = 'https://www.googleapis.com/auth/spreadsheets'


def _load_client_secret():
    if not os.path.isfile(CLIENT_SECRET_PATH):
        raise SystemExit(
            f'Missing {CLIENT_SECRET_PATH} — download an OAuth Client ID (Desktop app) from '
            'Google Cloud Console and save it there first. See README.md in this directory.'
        )
    with open(CLIENT_SECRET_PATH) as f:
        data = json.load(f)
    return data['installed']


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        qs = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(qs)
        self.server.auth_code = params.get('code', [None])[0]
        self.server.auth_error = params.get('error', [None])[0]
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        msg = 'Autorisation reçue, tu peux fermer cet onglet.' if self.server.auth_code else \
            f'Erreur d\'autorisation : {self.server.auth_error}'
        self.wfile.write(f'<html><body>{msg}</body></html>'.encode('utf-8'))

    def log_message(self, *args):
        pass  # silence default request logging to stderr


def _run_authorize_flow():
    client = _load_client_secret()
    client_id = client['client_id']
    client_secret = client['client_secret']
    auth_uri = client.get('auth_uri', 'https://accounts.google.com/o/oauth2/v2/auth')
    token_uri = client.get('token_uri', 'https://oauth2.googleapis.com/token')

    server = http.server.HTTPServer(('localhost', 0), _CallbackHandler)
    port = server.server_address[1]
    redirect_uri = f'http://localhost:{port}/'
    server.auth_code = None
    server.auth_error = None

    verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).rstrip(b'=').decode('ascii')
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode('ascii')).digest()
    ).rstrip(b'=').decode('ascii')

    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': SCOPE,
        'access_type': 'offline',
        'prompt': 'consent',
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    url = auth_uri + '?' + urllib.parse.urlencode(params)
    print('Ouvre cette URL dans un navigateur, connecte-toi avec mayou.nkensa@gmail.com, et '
          'accorde l\'accès à Google Sheets :\n')
    print(url)
    print('\nEn attente de l\'autorisation (5 min max)...')

    thread = threading.Thread(target=server.handle_request)
    thread.start()
    thread.join(timeout=300)
    if not server.auth_code:
        raise SystemExit(f'Timeout ou autorisation refusée (error={server.auth_error}).')

    data = urllib.parse.urlencode({
        'client_id': client_id,
        'client_secret': client_secret,
        'code': server.auth_code,
        'code_verifier': verifier,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri,
    }).encode('ascii')
    req = urllib.request.Request(token_uri, data=data, method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemExit(f'Échange du code contre un jeton refusé : {e.read().decode("utf-8")}')

    token_data['obtained_at'] = time.time()
    token_data['client_id'] = client_id
    token_data['client_secret'] = client_secret
    token_data['token_uri'] = token_uri
    os.makedirs(SECRETS_DIR, exist_ok=True)
    with open(TOKEN_PATH, 'w') as f:
        json.dump(token_data, f, indent=2)
    os.chmod(TOKEN_PATH, 0o600)
    print(f'Autorisation réussie — jeton mis en cache dans {TOKEN_PATH}.')


def get_access_token():
    """Returns a valid access token, refreshing the cached one if needed. Raises (SystemExit)
    if no cached token exists yet — run `python3 sheets_oauth.py --authorize` once first."""
    if not os.path.isfile(TOKEN_PATH):
        raise SystemExit(
            f'Aucun jeton en cache ({TOKEN_PATH}) — lance d\'abord :\n'
            f'  python3 {os.path.abspath(__file__)} --authorize'
        )
    with open(TOKEN_PATH) as f:
        token_data = json.load(f)

    expires_in = token_data.get('expires_in', 3600)
    obtained_at = token_data.get('obtained_at', 0)
    if time.time() < obtained_at + expires_in - 60:  # 60s safety margin
        return token_data['access_token']

    refresh_token = token_data.get('refresh_token')
    if not refresh_token:
        raise SystemExit(
            'Jeton expiré et aucun refresh_token disponible — relance :\n'
            f'  python3 {os.path.abspath(__file__)} --authorize'
        )
    data = urllib.parse.urlencode({
        'client_id': token_data['client_id'],
        'client_secret': token_data['client_secret'],
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }).encode('ascii')
    req = urllib.request.Request(token_data['token_uri'], data=data, method='POST')
    try:
        with urllib.request.urlopen(req) as resp:
            refreshed = json.load(resp)
    except urllib.error.HTTPError as e:
        raise SystemExit(
            f'Rafraîchissement du jeton refusé ({e.read().decode("utf-8")}) — relance :\n'
            f'  python3 {os.path.abspath(__file__)} --authorize'
        )

    token_data['access_token'] = refreshed['access_token']
    token_data['expires_in'] = refreshed.get('expires_in', 3600)
    token_data['obtained_at'] = time.time()
    with open(TOKEN_PATH, 'w') as f:
        json.dump(token_data, f, indent=2)
    return token_data['access_token']


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--authorize', action='store_true', help='Run the one-time interactive OAuth flow.')
    args = p.parse_args()
    if args.authorize:
        _run_authorize_flow()
    else:
        print(get_access_token())
