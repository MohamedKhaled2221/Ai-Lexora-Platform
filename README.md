# M5 Public API Delivery

M5 public API contract:
- POST /clauses/analyze
- GET /health

M1 owns POST /ingest and POST /clauses.

The FastAPI adapter is intentionally thin. Connect `run_m5_analysis()` in
`app/main.py` to the existing M5 pipeline and M5→M6 adapter before
end-to-end use.

---

## Environment and dependency authority

**`requirements.txt` (+ `requirements-dev.txt`) is the source of truth for the
runtime environment.** It is what `qdrant_data\rebuild_venv.ps1` installs from,
and it is the only dependency file that has ever been used to build the venv
the M3 baseline and test suite were validated on.

`uv.lock` is kept in sync but is **not** used by the recovery path. Nothing
runs `uv sync`. It is retained so `pyproject.toml` remains resolvable and so a
future move to `uv sync` starts from a coherent state, not so anyone installs
from it today.

### How they relate

`requirements.txt` is *generated*, not hand-written — its own header records
the command:

```
uv export --locked --no-dev --no-hashes --output-file requirements.txt
```

So the real chain is:

```
pyproject.toml  --uv lock-->  uv.lock  --uv export-->  requirements.txt
```

**Do not hand-edit `requirements.txt` or `uv.lock`** — both are regenerated and
your edit disappears. (This is also why the authority note lives here and in
`pyproject.toml` rather than as a comment at the top of `uv.lock`: `uv lock`
rewrites that file wholesale and would strip it.) To change a dependency, edit
`pyproject.toml`, then re-run the two commands above.

### Verified state (2026-09-09)

- `requirements.txt` + `requirements-dev.txt`: **127 pinned packages**
- `uv.lock`: 130 (the extra three are the project itself plus `iniconfig` and
  `pluggy`, transitive test deps that the dev requirements do not pin directly)
- **Version mismatches between the two files: 0**
- **`requirements.txt` vs the installed venv: 0 mismatches**

That agreement is new. `pyproject.toml` previously declared
`pytest>=7.0.0`, `pytest-asyncio>=1.4.0` and `python-multipart==0.0.32`, which
resolved `uv.lock` to pytest 9.1.1 / pytest-asyncio 1.4.0 / python-multipart
0.0.32 — none of which is what the suite was validated on, and the
`pytest-asyncio` constraint actively *excluded* the installed 1.2.0. The dev
group is now pinned to the validated versions.

### Python version

**3.14.** Declared in three places, all agreeing as of 2026-09-09:
`.python-version`, `pyproject.toml` (`requires-python`) and `uv.lock`. They
previously all said 3.12 while the project ran on 3.14 — and because CPython
3.12.10 *is* installed on this host, `uv venv` here silently built a 3.12
environment rather than failing. See `qdrant_data\rebuild_venv.ps1`.
