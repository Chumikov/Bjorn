# Test Coverage Status

## Gate

Current gate: `--cov-fail-under=25` (in `pytest.ini`).
Aspirational target: 50% overall, 70% new code.

## Baseline (start of v1.3.0, after Stage -1 infrastructure setup)

- Total coverage: **17.77%**
- Tests: 73 passing
- Untested modules (~0%): `Bjorn.py`, `orchestrator.py`, `display.py`, `comment.py`,
  `epd_helper.py`, `scanning.py`, all `*_connector.py` except `rdp_connector.py`,
  all `steal_files_*.py`, `sql_connector.py`, `log_standalone*.py`.

## Strategy

v1.3.0 work adds ~30-40 regression tests focused on the bug fixes. Each task
has at least one new test (see `Develop_Plan.md` Phase 0–11). Expected end-state
of v1.3.0: ~35–40% overall coverage.

The 50% target requires backfilling tests for currently-untouched modules
(`Bjorn.py`, `orchestrator.py`, `display.py`, `comment.py`). That is scheduled
for v1.4.0 (see PORT-* and MIGR-* phases).

## Running tests

```bash
# Full suite with coverage gate
pytest

# Fast iteration (skip coverage)
pytest --no-cov

# Just one test file
pytest tests/test_logger.py -v

# View HTML coverage report
pytest && open coverage_html_report/index.html
```

## Files

- `pytest.ini` — pytest configuration, coverage gate
- `.coveragerc` — coverage source/omit rules
- `requirements-dev.txt` — `pytest-cov`, `pytest-timeout`
- `tests/conftest.py` — shared fixtures
