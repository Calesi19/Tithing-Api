# Wells Fargo Tithing API

Upload a **Wells Fargo** CSV export and compute a tithing amount (default **10%**) for deposits whose description contains a given substring (default: `MILLWORK DEV PAYROLL`) within a date range.

Built with **FastAPI** and **uv**.

## Features

- Accepts Wells Fargo CSV (quoted rows with columns: Date, Amount, Type, Category, Description)
- Filters by date range (inclusive)
- Matches deposits by substring in the Description field (case-insensitive by default)
- Sums **positive** Amounts only (credits/deposits)
- Returns JSON summary **or** downloadable CSV (with per-row tithe and totals)
- Clear errors with line numbers for malformed rows

## Requirements

- Python 3.13
- [uv](https://github.com/astral-sh/uv)

## Quickstart

```bash
# clone and enter the repo
git clone https://github.com/Calesi19/Tithing-Api.git
cd Tithing-Api

# install deps
uv sync

# run in dev with hot reload
uv run dev
# or using uvx
uvx uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Example Request

```bash
curl -L -X POST "http://localhost:8000/tithing?start=2025-05-27&end=2025-09-30&desc_contains=MWD%20MILLWORK%20DEV%20PAYROLL&format=csv" \
        -F "file=@./bank.csv"
```
