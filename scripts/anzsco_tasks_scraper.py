#!/usr/bin/env python3
"""
Fetch ANZSCO unit-group "Tasks" (responsibilities) from the ABS classification
website and merge them into every 6-digit occupation.

Produces an updated occupations-database.json where every occupation gains:
  - tasks: ["Designing electrical systems ...", ...]  (verbatim bullets)
  - responsibilities: alias of tasks for admin UI convenience

Scraper is polite: caches each unit-group page to disk, 1 req/sec, retries on
500s. Safe to re-run; nothing is deleted or overwritten unless --force is set.
"""
import json
import os
import re
import sys
import time
import hashlib
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup  # type: ignore
except ImportError:
    sys.stderr.write("Install deps: pip install requests beautifulsoup4\n")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "public" / "occupations-database.json"
CACHE_DIR = ROOT / "scripts" / ".cache" / "anzsco_tasks"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (compatible; MigrateAU-TasksScraper/1.0; "
    "+https://migrateau-admin-205705.web.app)"
)

ABS_BASE = (
    "https://www.abs.gov.au/statistics/classifications/"
    "anzsco-australian-and-new-zealand-standard-classification-occupations/"
    "2022/browse-classification/"
)


def unit_group_url(unit: str) -> str:
    major = unit[0]
    sub = unit[:2]
    minor = unit[:3]
    return f"{ABS_BASE}{major}/{sub}/{minor}/{unit}"


def cached_fetch(url: str) -> str | None:
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    cached = CACHE_DIR / f"{key}.html"
    if cached.exists():
        return cached.read_text(encoding="utf-8")

    for attempt in range(3):
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            if r.status_code == 404:
                return None
            if r.status_code >= 500:
                time.sleep(2 + attempt * 2)
                continue
            r.raise_for_status()
            cached.write_text(r.text, encoding="utf-8")
            time.sleep(1.1)  # polite
            return r.text
        except Exception as e:
            print(f"  [tasks] attempt {attempt+1} failed for {url}: {e}")
            time.sleep(2 + attempt * 2)
    return None


def extract_tasks(html: str) -> list[str]:
    """
    ABS pages have a section titled 'Tasks Include:' or 'Tasks' with a <ul>
    of bullet points. Return the list of task strings. Falls back to empty.
    """
    soup = BeautifulSoup(html, "html.parser")
    tasks: list[str] = []

    # Approach 1: find a heading whose text starts with 'Tasks'
    for tag in soup.find_all(["h2", "h3", "h4", "strong", "b"]):
        text = (tag.get_text() or "").strip()
        if re.match(r"(?i)^tasks\b", text):
            ul = tag.find_next("ul")
            if ul:
                for li in ul.find_all("li"):
                    t = re.sub(r"\s+", " ", li.get_text(" ", strip=True)).strip()
                    if 10 < len(t) < 600:
                        tasks.append(t)
            if tasks:
                return tasks

    # Approach 2: any <p> starting with 'Tasks include:' followed by a <ul>
    for p in soup.find_all("p"):
        text = (p.get_text() or "").strip().lower()
        if "task" in text and "include" in text:
            ul = p.find_next("ul")
            if ul:
                for li in ul.find_all("li"):
                    t = re.sub(r"\s+", " ", li.get_text(" ", strip=True)).strip()
                    if 10 < len(t) < 600:
                        tasks.append(t)
            if tasks:
                return tasks

    return tasks


def main() -> None:
    force = "--force" in sys.argv
    data = json.loads(DB_PATH.read_text())
    occupations = data.get("occupations", [])
    unit_groups: dict[str, str] = {}
    for occ in occupations:
        code = str(occ.get("anzsco") or "").strip()
        if len(code) >= 6:
            unit = code[:4]
            unit_groups.setdefault(unit, occ.get("unitGroup") or "")

    print(f"Found {len(unit_groups)} unit groups to scan.")
    results: dict[str, list[str]] = {}
    for i, (unit, name) in enumerate(sorted(unit_groups.items()), 1):
        print(f"[{i}/{len(unit_groups)}] {unit} {name}")
        url = unit_group_url(unit)
        html = cached_fetch(url)
        if not html:
            continue
        tasks = extract_tasks(html)
        if tasks:
            results[unit] = tasks
            print(f"  → {len(tasks)} tasks")

    merged = 0
    skipped = 0
    for occ in occupations:
        code = str(occ.get("anzsco") or "").strip()
        unit = code[:4]
        tasks = results.get(unit)
        if not tasks:
            continue
        if occ.get("tasks") and not force:
            skipped += 1
            continue
        occ["tasks"] = tasks
        occ["responsibilities"] = tasks  # alias used by admin UI
        merged += 1

    data.setdefault("counts", {})
    data["counts"]["withTasks"] = sum(1 for o in occupations if o.get("tasks"))
    data["counts"]["unitGroupsWithTasks"] = len(results)

    DB_PATH.write_text(json.dumps(data, indent=2) + "\n")
    print(f"\nMerged tasks into {merged} occupations (skipped {skipped} already present).")
    print(f"Total occupations with tasks: {data['counts']['withTasks']}/{len(occupations)}")


if __name__ == "__main__":
    main()
