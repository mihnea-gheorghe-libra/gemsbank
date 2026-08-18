# `ops/ci` — CI support scripts

The workflow itself lives in `.github/workflows/ci.yml`. Shared shell scripts and helpers used by
it belong here.

## What CI must run

| Job | Command | Blocks merge |
|---|---|---|
| Lint | `make lint` (ruff + eslint) | yes |
| Types | `make types` (`mypy --strict` on `platform/` and `modules/*/domain`; `tsc --noEmit`) | yes |
| Tests | `make test` (pytest + Playwright smoke) | yes |
| Architecture | the `tests/architecture/` suite | **yes — never make this advisory** |
| Contract drift | regenerate OpenAPI, fail if the committed contract differs | yes |

## The architecture job

It is a separate, clearly named job so that a failure reads as *"you crossed a boundary"* rather
than as a mysterious test failure among two hundred others.

Do not let it become advisory. The moment a boundary check only warns, it stops being a boundary
(ADR 0001).
