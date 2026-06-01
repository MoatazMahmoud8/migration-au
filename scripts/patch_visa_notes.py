#!/usr/bin/env python3
"""
patch_visa_notes.py
===================
Fixes inaccurate visa notes / labels in state-occupation-requirements.json:

  - SC 190 "State sponsorship increases priority"
      → "State nomination is REQUIRED — you cannot apply without it"
  - SC 190 'visa' label "Skilled Independent" → "Skilled Nominated"
  - SC 491 prepends mandatory-nomination note
  - SC 482 visa label / TSMIT minimum salary fix

Preserves the graduatePathways block and hasGraduatePathway flags.
"""
import json
import os
from pathlib import Path

PATH = Path(__file__).parent.parent / "public" / "state-occupation-requirements.json"

with open(PATH) as f:
    data = json.load(f)

reqs = data.get("requirements", {})
patched = {"190": 0, "491": 0, "482": 0}

GRAD_PREFIX = "🎓"  # don't dedupe these

for anzsco, by_state in reqs.items():
    for state, by_visa in by_state.items():
        # ── SC 190 ─────────────────────────────────────────────────────────
        r190 = by_visa.get("190")
        if r190:
            if r190.get("visa") in ("SC 190 Skilled Independent",):
                r190["visa"] = "SC 190 Skilled Nominated"
            r190["stream"] = "Points-based + State nomination (mandatory)"
            r190["stateSponsorship"] = "Required (mandatory)"

            notes = r190.get("notes", [])
            grad_notes = [n for n in notes if n.startswith(GRAD_PREFIX)]
            notes = [n for n in notes if n != "State sponsorship increases priority"]
            mandatory = "State nomination is REQUIRED — you cannot apply without it"
            if mandatory not in notes:
                notes.insert(0, mandatory)
            # Ensure points note mentions the +5 bonus
            for i, n in enumerate(notes):
                if "Minimum 65 points on points test" == n:
                    notes[i] = "Minimum 65 points on points test (state nomination adds 5 pts)"
            # Keep graduate notes at the end
            non_grad = [n for n in notes if not n.startswith(GRAD_PREFIX)]
            r190["notes"] = non_grad + grad_notes
            patched["190"] += 1

        # ── SC 491 ─────────────────────────────────────────────────────────
        r491 = by_visa.get("491")
        if r491:
            r491["visa"] = "SC 491 Skilled Work Regional"
            r491["stream"] = "Regional + Points-based + State nomination (mandatory)"
            r491["stateSponsorship"] = "Required (state or family sponsor)"
            notes = r491.get("notes", [])
            grad_notes = [n for n in notes if n.startswith(GRAD_PREFIX)]
            mandatory = "State nomination OR eligible family sponsor is REQUIRED"
            if mandatory not in notes:
                notes.insert(0, mandatory)
            non_grad = [n for n in notes if not n.startswith(GRAD_PREFIX)]
            r491["notes"] = non_grad + grad_notes
            patched["491"] += 1

        # ── SC 482 ─────────────────────────────────────────────────────────
        r482 = by_visa.get("482")
        if r482:
            r482["visa"] = "SC 482 Skills in Demand"
            r482["stream"] = "Employer-sponsored (mandatory)"
            r482["stateSponsorship"] = "Not applicable (employer-sponsored instead)"
            # TSMIT floor 2024 — bump salary if below
            if isinstance(r482.get("minSalary"), (int, float)) and r482["minSalary"] < 73150:
                r482["minSalary"] = 73150
            notes = r482.get("notes", [])
            grad_notes = [n for n in notes if n.startswith(GRAD_PREFIX)]
            mandatory = "Job offer from an approved sponsoring employer is REQUIRED"
            if mandatory not in notes:
                notes.insert(0, mandatory)
            non_grad = [n for n in notes if not n.startswith(GRAD_PREFIX)]
            r482["notes"] = non_grad + grad_notes
            patched["482"] += 1

with open(PATH, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

size_mb = os.path.getsize(PATH) / (1024 * 1024)
print(f"✓ Patched 190: {patched['190']}, 491: {patched['491']}, 482: {patched['482']}")
print(f"✓ File size: {size_mb:.1f} MB")
