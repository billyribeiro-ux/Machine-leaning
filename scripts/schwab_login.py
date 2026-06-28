#!/usr/bin/env python3
"""
Schwab OAuth helper — completes the one step that needs a human.

Schwab uses three-legged OAuth: you must log in to your *brokerage* account in
a browser and authorize the app. This script handles everything around that:

  1. Prints the authorization URL (open it in your browser, log in, approve).
  2. Schwab redirects to your callback (https://127.0.0.1?code=...&session=...).
     Copy the FULL redirected URL from the address bar.
  3. Paste it here. The script extracts + URL-decodes the code, exchanges it
     for access + refresh tokens, and saves the refresh token to .env.

After this, every other Schwab call works headlessly (the refresh token lasts
7 days; the adapter auto-refreshes the 30-minute access token).

Usage:
    python scripts/schwab_login.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

ENV_PATH = ROOT / ".env"
load_dotenv(ENV_PATH)

from src.scanify.schwab_adapter import SchwabAdapter  # noqa: E402


def extract_code(pasted: str) -> str:
    """Accept either a full redirect URL or a raw code; return the decoded code."""
    pasted = pasted.strip()
    if pasted.startswith("http"):
        q = parse_qs(urlparse(pasted).query)
        code = q.get("code", [""])[0]
    else:
        code = pasted
    return unquote(code)


def save_refresh_token(token: str) -> None:
    text = ENV_PATH.read_text() if ENV_PATH.exists() else ""
    if re.search(r"^SCANIFY_SCHWAB_REFRESH_TOKEN=.*$", text, flags=re.M):
        text = re.sub(r"^SCANIFY_SCHWAB_REFRESH_TOKEN=.*$",
                      f"SCANIFY_SCHWAB_REFRESH_TOKEN={token}", text, flags=re.M)
    else:
        text += f"\nSCANIFY_SCHWAB_REFRESH_TOKEN={token}\n"
    ENV_PATH.write_text(text)


def main() -> None:
    schwab = SchwabAdapter()
    if not schwab.is_configured:
        print("ERROR: set SCANIFY_SCHWAB_CLIENT_ID and SCANIFY_SCHWAB_CLIENT_SECRET in .env")
        sys.exit(1)

    print("=" * 70)
    print("  SCHWAB OAUTH LOGIN")
    print("=" * 70)
    print("\n1) Open this URL in your browser, log in, and approve the app:\n")
    print("   " + schwab.get_authorization_url())
    print("\n2) After approving you'll be redirected to a URL starting with")
    print("   https://127.0.0.1?code=...  (the page may show a browser error —")
    print("   that's fine, just copy the FULL URL from the address bar).")
    print()

    pasted = input("3) Paste the full redirected URL (or just the code) here:\n> ")
    code = extract_code(pasted)
    if not code:
        print("ERROR: could not find an authorization code in that input.")
        sys.exit(1)

    print("\nExchanging code for tokens ...")
    try:
        tok = schwab.exchange_authorization_code(code)
    except Exception as exc:
        print(f"ERROR: token exchange failed: {exc}")
        print("Common causes: code expired (they last ~30s — retry fast), or the")
        print("callback URL in the Schwab app dashboard doesn't match the redirect_uri.")
        sys.exit(1)

    refresh = tok.get("refresh_token")
    if refresh:
        save_refresh_token(refresh)
        print("\n✅ Success. Refresh token saved to .env (SCANIFY_SCHWAB_REFRESH_TOKEN).")
        print("   Schwab is now connected — quotes, options chains and price history")
        print("   will work headlessly. Test with:  python scripts/schwab_check.py")
    else:
        print("Token exchange returned no refresh_token:", tok)


if __name__ == "__main__":
    main()
