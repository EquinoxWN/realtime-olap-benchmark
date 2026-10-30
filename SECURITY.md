# Security policy

## Reporting a vulnerability

Please report security problems privately through GitHub:
**Security > Report a vulnerability** on this repository
(`https://github.com/EquinoxWN/realtime-olap-benchmark/security/advisories/new`). Do not open a public issue.

Include what you found, how to reproduce it, and the impact you expect. You will get an answer
within 7 days. Fixes are released as soon as they are ready, and you are credited unless you ask
not to be.

## Supported versions

This project is pre-1.0. Only the latest commit on `main` receives fixes.

## Scope

- **In scope:** SQL or path injection through query files, data files or result files; credentials leaking into URLs, logs or result files; unbounded reads of server responses or result files; Docker settings that expose an engine beyond the local machine.
- **Out of scope:** Vulnerabilities in ClickHouse, Apache Doris, StarRocks or DuckDB themselves (report those upstream).

## How this repository protects itself

- Every GitHub Action is pinned to a full commit SHA, and workflows run with read-only
  permissions and without persisted credentials.
- Dependabot update pull requests are paused (`open-pull-requests-limit: 0`) so the repository keeps a single `main` branch; dependencies are updated by hand and checked by the CI audit.
- CI runs lint, tests and a known-vulnerability check (pip-audit) on every push and pull request.
- Container images are pinned by digest; ClickHouse and StarRocks ports bind to 127.0.0.1, and the CI ClickHouse password is random per run and masked in logs.
