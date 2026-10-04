#!/usr/bin/env python3
"""
Fetch the full ANZSCO 2022 occupation hierarchy from the official ABS workbook.

This replaces the earlier Jobs and Skills Australia sitemap approximation, which
only yielded a subset of occupations and caused the app/database to miss many
official ANZSCO six-digit codes.
"""

from __future__ import annotations

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

ABS_STRUCTURE_URL = (
    "https://www.abs.gov.au/statistics/classifications/"
    "anzsco-australian-and-new-zealand-standard-classification-occupations/2022/"
    "anzsco%202022%20structure%20062023.xlsx"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
}

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "public" / "all-anzsco-occupations.json"

NS_MAIN = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_REL = {"r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
NS_PKG_REL = {"pr": "http://schemas.openxmlformats.org/package/2006/relationships"}


def fetch_workbook() -> bytes:
    req = urllib.request.Request(ABS_STRUCTURE_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    value = 0
    for ch in letters:
        value = value * 26 + (ord(ch.upper()) - 64)
    return value - 1


def parse_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    values: list[str] = []
    for si in root.findall("x:si", NS_MAIN):
        parts = []
        for text_node in si.findall(".//x:t", NS_MAIN):
            parts.append(text_node.text or "")
        values.append("".join(parts))
    return values


def workbook_sheet_paths(zf: zipfile.ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels.findall("pr:Relationship", NS_PKG_REL)
    }

    mapping: dict[str, str] = {}
    for sheet in workbook.findall("x:sheets/x:sheet", NS_MAIN):
        name = sheet.attrib["name"]
        rel_id = sheet.attrib[f"{{{NS_REL['r']}}}id"]
        target = rel_map[rel_id]
        mapping[name] = target if target.startswith("xl/") else f"xl/{target}"
    return mapping


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        text = cell.find("x:is/x:t", NS_MAIN)
        return text.text.strip() if text is not None and text.text else ""

    raw = cell.findtext("x:v", default="", namespaces=NS_MAIN)
    if raw == "":
        return ""

    if cell_type == "s":
        return shared_strings[int(raw)]
    return raw.strip()


def read_sheet_rows(zf: zipfile.ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(zf.read(sheet_path))
    rows: list[list[str]] = []
    for row in root.findall(".//x:sheetData/x:row", NS_MAIN):
        values: list[str] = []
        for cell in row.findall("x:c", NS_MAIN):
            idx = column_index(cell.attrib.get("r", "A1"))
            while len(values) <= idx:
                values.append("")
            values[idx] = cell_value(cell, shared_strings)
        rows.append(values)
    return rows


def parse_table_five(rows: list[list[str]]) -> dict[str, object]:
    occupations: list[dict[str, object]] = []
    seen_codes: set[str] = set()
    major_groups: dict[str, str] = {}
    sub_major_groups: dict[str, str] = {}
    minor_groups: dict[str, str] = {}
    unit_groups: dict[str, str] = {}

    current_major = ""
    current_sub_major = ""
    current_minor = ""
    current_unit = ""

    for row in rows:
        major_code = row[0].strip() if len(row) > 0 else ""
        major_title = row[1].strip() if len(row) > 1 else ""
        sub_major_code = row[1].strip() if len(row) > 1 else ""
        sub_major_title = row[2].strip() if len(row) > 2 else ""
        minor_code = row[2].strip() if len(row) > 2 else ""
        minor_title = row[3].strip() if len(row) > 3 else ""
        unit_code = row[3].strip() if len(row) > 3 else ""
        unit_title = row[4].strip() if len(row) > 4 else ""
        occupation_code = row[4].strip() if len(row) > 4 else ""
        occupation_title = row[5].strip() if len(row) > 5 else ""
        skill_level = row[6].strip() if len(row) > 6 else ""

        if re.fullmatch(r"[1-8]", major_code) and major_title:
            current_major = major_code
            major_groups[current_major] = major_title

        if re.fullmatch(r"\d{2}", sub_major_code) and sub_major_title:
            current_sub_major = sub_major_code
            sub_major_groups[current_sub_major] = sub_major_title

        if re.fullmatch(r"\d{3}", minor_code) and minor_title:
            current_minor = minor_code
            minor_groups[current_minor] = minor_title

        if re.fullmatch(r"\d{4}", unit_code) and unit_title:
            current_unit = unit_code
            unit_groups[current_unit] = unit_title

        if not re.fullmatch(r"\d{6}", occupation_code) or not occupation_title:
            continue
        if occupation_code in seen_codes:
            continue

        occupations.append({
            "anzsco": occupation_code,
            "name": occupation_title,
            "lists": [],
            "visas": [],
            "assessingAuthority": None,
            "group": major_groups.get(current_major, "Various"),
            "majorGroup": f"{current_major} {major_groups[current_major]}" if current_major in major_groups else None,
            "subMajorGroup": f"{current_sub_major} {sub_major_groups[current_sub_major]}" if current_sub_major in sub_major_groups else None,
            "minorGroup": f"{current_minor} {minor_groups[current_minor]}" if current_minor in minor_groups else None,
            "unitGroup": f"{current_unit} {unit_groups[current_unit]}" if current_unit in unit_groups else None,
            "skillLevel": skill_level or None,
        })
        seen_codes.add(occupation_code)

    return {
        "occupations": occupations,
        "counts": {
            "majorGroups": len(major_groups),
            "subMajorGroups": len(sub_major_groups),
            "minorGroups": len(minor_groups),
            "unitGroups": len(unit_groups),
            "occupations": len(occupations),
        },
    }


def main() -> int:
    print("=== Fetch Full ANZSCO from ABS ===\n")
    workbook_bytes = fetch_workbook()
    with zipfile.ZipFile(BytesIO(workbook_bytes)) as zf:
        shared_strings = parse_shared_strings(zf)
        sheet_paths = workbook_sheet_paths(zf)
        rows = read_sheet_rows(zf, sheet_paths["Table 5"], shared_strings)

    parsed = parse_table_five(rows)
    occupations = parsed["occupations"]
    counts = parsed["counts"]
    now = datetime.now(timezone.utc)

    output = {
        "snapshotDate": now.strftime("%Y-%m-%d"),
        "lastUpdated": now.isoformat(),
        "source": ABS_STRUCTURE_URL,
        "counts": counts,
        "items": occupations,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2))

    print("✅ Done!")
    print(f"   Major Groups:     {counts['majorGroups']}")
    print(f"   Sub-Major Groups: {counts['subMajorGroups']}")
    print(f"   Minor Groups:     {counts['minorGroups']}")
    print(f"   Unit Groups:      {counts['unitGroups']}")
    print(f"   Occupations:      {counts['occupations']}")
    print(f"   Saved to:         {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
