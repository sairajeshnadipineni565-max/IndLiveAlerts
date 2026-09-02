"""
Fyers daily auth helper.

Fyers access tokens are valid only until market close on the day they're
issued, so a fresh one is needed every trading day.

TWO WAYS THIS RUNS, DEPENDING ON CONTEXT:

1. LOCAL (interactive) -- run this file directly each morning on your own
   machine:
     python fyers_auth.py
   It prints a login URL, you open it, log into Fyers, get redirected with
   an auth_code in the query string, and paste that back in. The resulting
   access token is printed for you to copy into the FYERS_ACCESS_TOKEN
   GitHub Secret (Settings -> Secrets and variables -> Actions -> update
   FYERS_ACCESS_TOKEN) before market opens -- also cached locally to
   access_token.txt for same-day local testing.

2. GITHUB ACTIONS (unattended) -- get_valid_token() just reads
   FYERS_ACCESS_TOKEN from the environment (the secret you pasted in step 1
   that morning). No browser, no TOTP, no PIN ever touches the runner.
   FYERS_CLIENT_ID is also needed there (non-sensitive on its own, but
   still passed as a secret for tidiness) -- FYERS_SECRET_KEY and
   FYERS_REDIRECT_URI are only used by the interactive local flow above and
   don't need to be set as GitHub Secrets at all.

If you forget to refresh the token some morning, the scheduled workflow
will simply fail fast with a clear "Fyers token not set" message (see the
preflight step in .github/workflows/) rather than partway through a run.
"""

import os
from datetime import date

TOKEN_FILE = "access_token.txt"
TOKEN_DATE_FILE = "access_token_date.txt"


def get_valid_token() -> str:
    """GitHub Actions: reads FYERS_ACCESS_TOKEN from the environment (the
    secret you pasted in this morning) -- this is the path used in prod.

    Local fallback: if that env var isn't set, falls back to today's cached
    access_token.txt (written by generate_token_interactive() below) so you
    can test scanner_in.py locally without re-exporting the env var every
    time you open a new shell."""
    env_token = os.environ.get("FYERS_ACCESS_TOKEN")
    if env_token:
        return env_token

    if os.path.exists(TOKEN_FILE) and os.path.exists(TOKEN_DATE_FILE):
        with open(TOKEN_DATE_FILE) as f:
            cached_date = f.read().strip()
        if cached_date == str(date.today()):
            with open(TOKEN_FILE) as f:
                return f.read().strip()

    raise RuntimeError(
        "No Fyers access token available. Either set FYERS_ACCESS_TOKEN "
        "(GitHub Secret, for Actions) or run `python fyers_auth.py` "
        "locally first to generate + cache one for today."
    )


def generate_token_interactive():
    from fyers_apiv3 import fyersModel
    from config_in import FYERS_CLIENT_ID, FYERS_SECRET_KEY, FYERS_REDIRECT_URI

    session = fyersModel.SessionModel(
        client_id=FYERS_CLIENT_ID,
        secret_key=FYERS_SECRET_KEY,
        redirect_uri=FYERS_REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code",
    )

    login_url = session.generate_authcode()
    print("\n1. Open this URL, log in, and approve access:\n")
    print(login_url)
    print("\n2. You'll be redirected to your redirect_uri with `auth_code=...` in the URL.")
    auth_code = input("3. Paste the auth_code here: ").strip()

    session.set_token(auth_code)
    response = session.generate_token()

    if "access_token" not in response:
        raise RuntimeError(f"Token generation failed: {response}")

    access_token = response["access_token"]
    with open(TOKEN_FILE, "w") as f:
        f.write(access_token)
    with open(TOKEN_DATE_FILE, "w") as f:
        f.write(str(date.today()))

    print("\nAccess token cached locally for today's local testing.")
    print("\n>>> Now copy the token below into your GitHub repo's FYERS_ACCESS_TOKEN")
    print(">>> secret (Settings -> Secrets and variables -> Actions) before market opens:\n")
    print(access_token)
    print()
    return access_token


if __name__ == "__main__":
    generate_token_interactive()
