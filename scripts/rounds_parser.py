import html as html_mod
import re
from datetime import datetime

from bs4 import BeautifulSoup


def unescape_embedded_html(raw: str) -> str:
    decoded = re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda match: chr(int(match.group(1), 16)),
        raw,
    )
    decoded = (
        decoded.replace('\\"', '"')
        .replace("\\/", "/")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
    )
    return html_mod.unescape(decoded)


def _parse_int(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def _parse_date(text: str) -> str | None:
    match = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if not match:
        return None
    try:
        return datetime.strptime(" ".join(match.groups()), "%d %B %Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _parse_tiebreak(text: str) -> str | None:
    match = re.search(r"\d{1,2}/(\d{1,2})/(\d{4})", text)
    if match:
        return f"{match.group(2)}-{int(match.group(1)):02d}"
    match = re.search(r"(\d{1,2})/(\d{4})", text)
    if match:
        return f"{match.group(2)}-{int(match.group(1)):02d}"
    return None


def _subclass(row_text: str) -> str | None:
    lowered = row_text.lower()
    if "189" in lowered and "independent" in lowered:
        return "189"
    if "491" in lowered and "family" in lowered:
        return "491"
    return None


def parse_current_round(raw_html: str) -> dict:
    soup = BeautifulSoup(unescape_embedded_html(raw_html), "html.parser")

    round_date = None
    for heading in soup.find_all(["h2", "h3", "h4", "h5"]):
        text = heading.get_text(" ", strip=True)
        if text.lower().startswith("invitations issued on"):
            round_date = _parse_date(text)
            if round_date:
                break
    if not round_date:
        raise ValueError("Current invitation-round date was not found")

    summary_totals: dict[str, int] = {}
    tie_breaks: dict[str, str | None] = {}
    monthly_totals: dict[str, int] = {}
    round_month = datetime.strptime(round_date, "%Y-%m-%d").strftime("%b").lower()

    for table in soup.find_all("table"):
        rows = [
            [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
            for row in table.find_all("tr")
        ]
        rows = [row for row in rows if row]
        if not rows:
            continue

        headers = [cell.strip().lower() for cell in rows[0]]
        if any("total eois invited" in header for header in headers):
            for cells in rows[1:]:
                subclass = _subclass(" ".join(cells))
                if subclass and len(cells) >= 2:
                    total = _parse_int(cells[1])
                    if total is not None:
                        summary_totals[subclass] = total
                        tie_breaks[subclass] = _parse_tiebreak(cells[2]) if len(cells) >= 3 else None

        month_index = next(
            (index for index, header in enumerate(headers) if header[:3] == round_month),
            None,
        )
        if headers[0] == "visa subclass" and month_index is not None:
            for cells in rows[1:]:
                subclass = _subclass(" ".join(cells))
                if subclass and len(cells) > month_index:
                    total = _parse_int(cells[month_index])
                    if total is not None:
                        monthly_totals[subclass] = total

    resolved: dict[str, int] = {}
    for subclass in ("189", "491"):
        summary_total = summary_totals.get(subclass)
        monthly_total = monthly_totals.get(subclass)
        if summary_total is not None and monthly_total is not None and summary_total != monthly_total:
            raise ValueError(
                f"SC {subclass} summary total {summary_total} does not match "
                f"the {round_month.title()} program-year total {monthly_total}"
            )
        total = summary_total if summary_total is not None else monthly_total
        if total is None:
            raise ValueError(f"SC {subclass} invitation total could not be verified")
        resolved[subclass] = total

    return {
        "date": round_date,
        "sc189Total": resolved["189"],
        "sc189TieBreak": tie_breaks.get("189"),
        "sc491FamilyTotal": resolved["491"],
        "sc491FamilyTieBreak": tie_breaks.get("491"),
    }