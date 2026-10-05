# Development and offline checks

Use Python 3.13 or later. From the repository root:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
PYTHON_DOTENV_DISABLED=1 python -m unittest discover -s tests -v
ruff check .
black --check .
mypy .
bandit -r . -ll -x ./.github,./docs,./templates,./.venv
vulture . --min-confidence 90 --exclude .github,docs,templates,.venv
radon cc app.py mist_connection.py tests -j | complexity-gate --max 15
pip-audit -r requirements.txt
```

Tests use Flask's test client and mocked SDK methods. They require no Mist API
token, devices, or live Mist service. Regression tests cover site discovery,
template and sitegroup caches, guest update payloads, and site-to-org fallback.
They were added and run before the complexity refactor.

The quality workflow runs the offline tests and the pinned development tools.
Radon checks application and test functions with a maximum complexity of 15.
Screenshot tooling is for documentation only; it is not a runtime dependency.
See [screenshot reproduction](screenshots/README.md).
