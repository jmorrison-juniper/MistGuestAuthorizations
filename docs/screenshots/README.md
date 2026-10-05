# Screenshot provenance

The seven PNG files in this directory are unaltered browser captures of
`templates/index.html`, served by the real Flask app. They show the dashboard,
edit dialog, blank and filled add dialogs, added guest, import dialog, and CSV
preview. They were captured on 2026-10-04 with a 1440 by 1080 viewport.

All organization, site, guest, client, token-name, and CSV data is fictional.
`docs/capture_screenshots.py` substitutes an in-memory connection for the Mist
SDK boundary and forbids live SDK sessions. Adding a guest changes only that
in-memory list. No Mist token is needed or read. Browser requests are restricted
to the local Flask server and the public Bootstrap assets on jsDelivr. Bootstrap
loads from the same CDN as the production template; it receives no guest data.

## Reproduce

From the repository root, install the development tools, then run:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
PYTHON_DOTENV_DISABLED=1 python -m docs.capture_screenshots
```

If Chromium or Microsoft Edge is already installed, skip the browser download
and set `SCREENSHOT_BROWSER` to its executable path. These captures used:

```bash
SCREENSHOT_BROWSER="/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge" \
  PYTHON_DOTENV_DISABLED=1 python -m docs.capture_screenshots
```

The script starts a loopback server on an unused port, performs actual UI
interactions, saves the PNG files, rejects unexpected network requests or
JavaScript errors, and stops the server. Modal animation and font rendering can
vary between platforms; these are documentation captures, not pixel snapshots.
