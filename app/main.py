from fastapi import FastAPI, UploadFile, File, Query, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, PlainTextResponse
from typing import List
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import csv
import io

APP_DESC = "Upload a Wells Fargo CSV export and compute 10% tithing on 'MILLWORK DEV PAYROLL' deposits within a date range."
app = FastAPI(title="Wells Fargo Tithing Calculator", description=APP_DESC, version="1.0.0")

DATE_FMT = "%m/%d/%Y"  # e.g., 09/15/2025

def parse_decimal(s: str) -> Decimal:
    if s is None:
        return Decimal("0")
    s = s.strip().replace(",", "")
    if s.startswith("+"):
        s = s[1:]
    try:
        return Decimal(s)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail=f"Invalid amount value: {s!r}")

def parse_date(s: str) -> date:
    try:
        return datetime.strptime(s.strip(), DATE_FMT).date()
    except Exception:
        raise HTTPException(status_code=400, detail=f"Invalid date value (expected MM/DD/YYYY): {s!r}")

def compute_tithe(total: Decimal, rate: Decimal) -> Decimal:
    return (total * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def iter_csv_rows(file_bytes: bytes):
    # Wells Fargo export tends to be quoted CSV with 5 fields:
    # 0: Date, 1: Amount (negatives are debits, positives are deposits), 2: Type/Check (often '*'),
    # 3: Empty/Category, 4: Description
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    for idx, row in enumerate(reader, start=1):
        if not row:
            continue
        if len(row) < 5:
            row = row + [""] * (5 - len(row))
        yield idx, row

@app.get("/", response_class=PlainTextResponse, summary="How to use")
def root():
    return (
        "POST /tithing with multipart/form-data:\n"
        "  - file: Wells Fargo CSV export\n"
        "Query params:\n"
        "  - start: YYYY-MM-DD (required)\n"
        "  - end:   YYYY-MM-DD (required, inclusive)\n"
        "  - desc_contains: default 'MILLWORK DEV PAYROLL'\n"
        "  - rate: tithe rate, default 0.10\n"
        "  - case_insensitive: true/false, default true\n"
        "  - format: 'json' or 'csv', default 'json'\n"
    )

@app.get("/health", summary="Health check")
def health():
    return {"status": "ok"}

@app.post("/tithing", summary="Upload CSV and compute tithe")
async def tithing(
    file: UploadFile = File(..., description="Wells Fargo CSV export file"),
    start: str = Query(..., description="Start date in YYYY-MM-DD"),
    end: str = Query(..., description="End date in YYYY-MM-DD (inclusive)"),
    desc_contains: str = Query("MILLWORK DEV PAYROLL", description="Substring to match in Description column"),
    rate: float = Query(0.10, ge=0.0, le=1.0, description="Tithe rate between 0 and 1"),
    case_insensitive: bool = Query(True, description="Case-insensitive description match"),
    format: str = Query("json", pattern="^(json|csv)$", description="Response format")
):
    try:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except Exception:
        raise HTTPException(status_code=400, detail="Dates must be in YYYY-MM-DD format")
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end must be on/after start")

    rate_dec = Decimal(str(rate))
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")

    needle = desc_contains.lower() if case_insensitive else desc_contains
    matches = []
    total = Decimal("0")
    errors: List[str] = []

    for line_no, row in iter_csv_rows(data):
        try:
            date_str, amount_str, _, _, desc = (row + [""] * 5)[:5]
            try:
                txn_date = parse_date(date_str)
            except HTTPException:
                if line_no == 1:
                    continue  # likely a header row
                else:
                    raise
            if not (start_date <= txn_date <= end_date):
                continue

            amount = parse_decimal(amount_str)
            if amount <= 0:
                continue  # only deposits/credits

            description = desc.strip()
            hay = description.lower() if case_insensitive else description
            if needle in hay:
                total += amount
                matches.append({
                    "date": txn_date.isoformat(),
                    "amount": f"{amount:.2f}",
                    "description": description
                })
        except HTTPException as he:
            errors.append(f"Line {line_no}: {he.detail}")
        except Exception as ex:
            errors.append(f"Line {line_no}: {type(ex).__name__}: {ex}")

    tithe = compute_tithe(total, rate_dec)

    if format == "csv":
        out = io.StringIO()
        w = csv.writer(out)
        w.writerow(["date", "amount", "description", f"tithe_{int(rate*100)}pct_per_row"])
        for r in matches:
            amt = Decimal(r["amount"])
            per = compute_tithe(amt, rate_dec)
            w.writerow([r["date"], f"{amt:.2f}", r["description"], f"{per:.2f}"])
        w.writerow([])
        w.writerow(["TOTAL", f"{total:.2f}", "", f"{tithe:.2f}"])
        out.seek(0)
        return StreamingResponse(iter([out.getvalue()]),
                                 media_type="text/csv",
                                 headers={"Content-Disposition": "attachment; filename=tithing_report.csv"})

    return JSONResponse({
        "filters": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "desc_contains": desc_contains,
            "rate": float(rate_dec),
            "case_insensitive": case_insensitive
        },
        "count": len(matches),
        "total_deposits": f"{total:.2f}",
        "tithe": f"{tithe:.2f}",
        "rows": matches,
        "errors": errors
    })
