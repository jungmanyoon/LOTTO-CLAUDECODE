# Repository Guidelines

## Project Structure & Module Organization
Keep the lotto prediction logic under `src/`. `src/core` coordinates pipelines, `src/filters` holds draw filters, `src/ml` wraps ensemble and LSTM models, `src/probabilistic` implements Bayesian and Monte Carlo engines, and `src/advanced` hosts optional analytics. Backtesting lives in `src/backtesting`, automation helpers in `automation`, monitoring probes in `monitoring`. Store raw inputs in `data`, caches in `cache` or `results`, trained artifacts in `models`, and generated reports in `docs` or `reports`. Tests mirror the layout under `tests`, and shared config templates reside in `configs`.

## Build, Test, and Development Commands
Run the end-to-end workflow with `python main.py`; add flags such as `--ml-only`, `--skip-fetch`, or `--no-parallel` to target specific stages. Refresh local benchmark dashboards via `python src/scripts/generate_benchmarks.py`. Execute the full regression suite with `python -m pytest`, or focus iterations with `pytest -m "unit"` and `pytest -m "integration"`. Produce HTML coverage artifacts using `pytest --cov=src --cov-report=html`.

## Coding Style & Naming Conventions
Format Python code with `black src tests` (120-character limit) and enforce linting through `flake8 src tests --max-line-length=120` followed by `pylint src`. Use 4-space indentation, snake_case for modules and functions, PascalCase for classes, and name tests `test_<feature>.py`. Align YAML keys with `config.yaml` using lowercase hyphenated identifiers.

## Testing Guidelines
Pytest discovery targets files named `test_*.py` under `tests/` as configured in `pytest.ini`. Mark slow workloads with `@pytest.mark.slow` and integration paths with `@pytest.mark.integration`, then exclude them during tight loops using `-m "not slow"`. Maintain deterministic seeds for ML fixtures and keep expected outputs in versioned fixtures. Coverage must remain above 70%, and fresh reports are expected after significant engine changes.

## Commit & Pull Request Guidelines
Write commits with concise, imperative subjects (e.g., `Improve threshold loader validation`) and add contextual bodies when behavior shifts. Pull requests should summarize intent, link relevant issues, attach accuracy or runtime metrics, include `pytest` evidence, and provide screenshots for UI or dashboard updates. Confirm `.github/workflows/tests.yml` succeeds locally and refresh `docs/` or `README.md` whenever you introduce new flags, behaviors, or configuration paths.

## Configuration & Data Tips
Create machine-specific overrides by copying `config.yaml` to `configs/local.yaml`, keeping secrets in environment variables consumed by `main.py`. Sanitize draw data before committing, document sources in `docs/`, and clear `cache/` and `results` after changing probabilistic settings to avoid stale analyses. Trained models belong in `models`; regenerate when training parameters shift.
