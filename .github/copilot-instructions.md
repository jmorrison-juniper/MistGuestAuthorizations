# `MistGuestAuthorizations` agent instructions

This file holds the rules that apply to `MistGuestAuthorizations` only. The rules that apply to each
repository of this owner are in `AGENTS.md` at the repository root. Read `AGENTS.md` first. This
file adds to it, and it does not hold a copy of a rule from it. Where the two files disagree, obey
`AGENTS.md` for a writing rule, a safety rule, or a security rule.

## What this repository is

MistGuestAuthorizations is a Flask portal for operators who manage guest WiFi access through Juniper Mist. The app uses Python 3.13 or later. Operators can manage MAC address authorizations for sites and WLANs from a browser. The container image targets Linux on amd64 and arm64.

## Language and environment

Use Python 3.13 or later and pip. From the repository root, create the environment and install the runtime and development packages:

```sh
python3.13 -m venv .venv && . .venv/bin/activate && python -m pip install -r requirements-dev.txt
```

The tests use mocked SDK methods and do not need a Mist API token. Set `PYTHON_DOTENV_DISABLED=1` when you run the tests.

## Local gates

Run these commands from the repository root. Each gate passes when its command exits with status 0.

| Gate | Command | Expected result |
| - | - | - |
| Compile | `python -m compileall -q app.py mist_connection.py docs tests` | Python files compile. |
| Lint | `ruff check .` | No lint findings. |
| Format | `black --check .` | No files need formatting. |
| Types | `mypy .` | No type errors. |
| Tests and documentation links | `PYTHON_DOTENV_DISABLED=1 python -m unittest discover -s tests -v` | All tests pass. |
| Security | `bandit -r . -ll -x ./.github,./docs,./templates,./.venv` | No high or medium findings. |
| Dependencies | `pip-audit -r requirements.txt` | No known vulnerabilities. |
| Complexity | `radon cc app.py mist_connection.py tests -j \| complexity-gate --max 15` | Each function has a complexity score of 15 or less. |
| Dead code | `vulture . --min-confidence 90 --exclude .github,docs,templates,.venv` | No dead code findings. |
| STE | `ste-linter --config .ste-linter.toml --min-score 80 README.md AGENTS.md .github/copilot-instructions.md` | Each file scores 80 or higher with the dictionary. |
| STE without dictionary | `STE_DICTIONARY_PATH=/nonexistent ste-linter --config .ste-linter.toml --min-score 80 README.md AGENTS.md .github/copilot-instructions.md` | Each file scores 80 or higher without the dictionary. |

## Architecture and conventions

`app.py` defines Flask routes and serves the health check. `mist_connection.py` wraps Mist SDK calls. `templates/index.html` provides the browser interface. `tests/` holds offline tests for routes, SDK calls, and documentation links. `docs/development.md` lists the local quality gates.

Keep tests offline. Mock Mist SDK calls instead of sending requests to a live Mist service.

## Safety in this repository

Caution: Revoking a guest authorization changes access in the live Mist service and can disconnect the device. Use mocked SDK calls in tests.

The application reads `MIST_APITOKEN` from the environment. Use `.env.example` to configure a local run. Do not commit `.env` or a real API token.

## Containers and ports

The Compose files do not set a project name. Compose uses the project directory name by default. The service listens on container port `5000`. The host port is `${PORT:-5000}`. This repository has no container test and no assigned free port range. Run the offline tests without starting a container.

| Port | Owner |
| - | - |
| 5000 | Flask application |

The Compose service sets the container name to `mistguestauthorizations`. Do not start this fixed-name service for a test.

## Git and GitHub in this repository

Use the `documentation` label for documentation work, the `ci` label for workflow work, and the `python` label for Python changes. Use the `in-progress` label while work is active.

The repository has no changelog, issue template, pull request template, CodeQL workflow, or `auto-merge` label. Main requires the offline application tests, the shared quality gates, and the container build checks. The shared gate workflow also syncs issues for failed gates on `main`.

| Workflow | Trigger and purpose |
| - | - |
| `quality-gates.yml` | Runs offline tests and shared Python gates on pull requests and pushes to `main`. |
| `build-and-push.yml` | Builds a container image for pull requests and pushes to `main`. It does not push an image for a pull request. |
| `ste-lint.yml` | Grades `README.md`, `AGENTS.md`, and this file on each pull request and on pushes to `main`. |
| `stranded-branch-report.yml` | Reports branches each Monday at 07:00 UTC and supports a manual run. |
| `release.yml` | Publishes a release for tags in `YY.MM.DD.HH.MM` format or a manual run with a version. |

Do not push a tag as part of a code change. A tag starts `release.yml`.

## Known pitfalls

- Issue #15 lowered measured code complexity before the Radon gate became required. Keep every measured function at or below the complexity limit of 15.

## Key files

| File | Purpose |
| - | - |
| `app.py` | Flask routes and application entry point. |
| `mist_connection.py` | Mist API session and authorization operations. |
| `templates/index.html` | Browser interface. |
| `tests/` | Offline application and documentation tests. |
| `docs/development.md` | Development setup and quality gate commands. |

## External resources

- [Juniper Mist API documentation](https://www.juniper.net/documentation/us/en/software/mist/api/http/getting-started)
- [Mist API Python SDK](https://github.com/tmunzer/mistapi_python)
- [Flask documentation](https://flask.palletsprojects.com/)
- [Bootstrap documentation](https://getbootstrap.com/docs/5.3/)
- [misthelper-devtools](https://github.com/jmorrison-juniper/misthelper-devtools)
