import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fpdf import FPDF

_HEADERS = ("Date", "Reference", "Counterparty", "Category", "Direction", "Amount")
_BUCHAREST = ZoneInfo("Europe/Bucharest")
_FONT_DIR = Path(__file__).resolve().parent / "fonts"


def _display_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).astimezone(_BUCHAREST).strftime("%d.%m.%Y")
    except ValueError:
        return iso


def _display_period_bound(iso: str | None, *, fallback: str) -> str:
    if iso is None:
        return fallback
    try:
        return datetime.fromisoformat(iso).date().strftime("%d.%m.%Y")
    except ValueError:
        return iso


def _period_label(data: dict[str, Any]) -> str:
    start = _display_period_bound(data["dateFrom"], fallback="account opening")
    end = _display_period_bound(data["dateTo"], fallback="today")
    return f"{start} - {end}"


def _amount_display(row: dict[str, Any]) -> str:
    minor = row["amount"]["minorUnits"]
    return f"{minor / 100:.2f}"


def _rows(data: dict[str, Any]) -> list[tuple[str, ...]]:
    return [
        (
            _display_date(row["postedAt"]),
            row["reference"],
            row["counterparty"],
            row["category"].capitalize(),
            row["direction"].capitalize(),
            _amount_display(row),
        )
        for row in data["movements"]
    ]


def render_csv(data: dict[str, Any]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    account = data["account"]
    currency = account["currency"]
    writer.writerow(["Account statement"])
    writer.writerow(["IBAN", account["iban"]])
    writer.writerow(["Holder", account["holderName"]])
    writer.writerow(["Currency", currency])
    writer.writerow(["Period", _period_label(data)])
    writer.writerow(["Opening balance", f"{data['openingBalanceMinor'] / 100:.2f}"])
    writer.writerow(["Closing balance", f"{data['closingBalanceMinor'] / 100:.2f}"])
    writer.writerow([])
    writer.writerow(_HEADERS)
    writer.writerows(_rows(data))
    return buffer.getvalue().encode("utf-8-sig")


class _StatementPdf(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("DejaVu", "", str(_FONT_DIR / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(_FONT_DIR / "DejaVuSans-Bold.ttf"))


def _fit(pdf: FPDF, text: str, width: float, pad: float = 3) -> str:
    budget = width - pad
    if pdf.get_string_width(text) <= budget:
        return text
    ellipsis = "…"
    while text and pdf.get_string_width(text + ellipsis) > budget:
        text = text[:-1]
    return (text + ellipsis) if text else ellipsis


def render_pdf(data: dict[str, Any]) -> bytes:
    account = data["account"]
    currency = account["currency"]

    pdf = _StatementPdf()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 10, "GEMS Bank — Account statement", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("DejaVu", "", 10)
    pdf.cell(0, 6, f"IBAN: {account['iban']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Holder: {account['holderName']}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Currency: {currency}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Period: {_period_label(data)}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Opening balance: {data['openingBalanceMinor'] / 100:.2f} {currency}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Closing balance: {data['closingBalanceMinor'] / 100:.2f} {currency}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    widths = (22.0, 42.0, 42.0, 26.0, 22.0, 26.0)
    pdf.set_font("DejaVu", "B", 9)
    for header, width in zip(_HEADERS, widths):
        pdf.cell(width, 7, _fit(pdf, header, width), border=1)
    pdf.ln()

    pdf.set_font("DejaVu", "", 9)
    for row in _rows(data):
        for value, width in zip(row, widths):
            pdf.cell(width, 6, _fit(pdf, value, width), border=1)
        pdf.ln()

    if not data["movements"]:
        pdf.set_font("DejaVu", "", 9)
        pdf.cell(0, 8, "No movements in this period.", new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
