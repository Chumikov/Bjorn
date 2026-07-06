# Test Coverage Status

## Gate

Current gate: `--cov-fail-under=25` (in `pytest.ini`).
Aspirational target: 50% overall, 70% new code.

## Текущее состояние (v1.4.0)

- Total coverage: **~34.4%**
- Tests: **352 passing**

## Baseline (start of v1.3.0, after Stage -1 infrastructure setup)

- Total coverage: **17.77%**
- Tests: 73 passing
- Untested modules (~0%): `Bjorn.py`, `orchestrator.py`, `display.py`, `comment.py`,
  `epd_helper.py`, `scanning.py`, all `*_connector.py` except `rdp_connector.py`,
  all `steal_files_*.py`, `sql_connector.py`, `log_standalone*.py`.

## Strategy

v1.3.0 добавила ~30-40 регрессионных тестов под баг-фиксы (по тесту на каждую
задачу, см. `Develop_Plan.md` Phase 0–11). Фактический результат v1.3.0–v1.3.4 —
покрытие выросло с 17.77% до ~34.4% (v1.3.0–v1.4.0: +175 тестов, +72 new tests in v1.4.0).
часть модулей вроде `display.py`, `orchestrator.py` остаются без поведенческих
тестов, только source-level AST-проверки).

Цель 50% требует backfill-а поведенческих тестов для нетронутых модулей
(`Bjorn.py`, `orchestrator.py`, `display.py`, `comment.py`). Запланировано на
v1.4.0 (фазы PORT-* / MIGR-*).

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
