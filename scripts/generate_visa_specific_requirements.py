#!/usr/bin/env python3
"""
Generate visa-specific state requirements for all occupations.

Consumes public/official-occupation-lists.json to flag each
(anzsco, state, visa) combination as 'sponsored' or 'not_sponsored'.

NOT on the official list   → status='not_sponsored', synthetic numbers omitted.
ON the official list       → status='sponsored', full requirements populated.
                              minSalary is null when source has no JSA data
                              (UI must render 'Salary data not available').

SC 190: Skilled Nominated — state nomination MANDATORY, permanent
SC 491: Skilled Work Regional — state OR family nomination MANDATORY, provisional 5yr
SC 482: Skills in Demand — employer sponsorship MANDATORY, temporary 1-4yr
"""
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"

print("Loading data...")
with open(PUBLIC / 'all-anzsco-occupations.json') as f:
    all_occ_data = json.load(f)
    all_occupations = {o['anzsco']: o for o in all_occ_data.get('items', [])}

with open(PUBLIC / 'salaries.json') as f:
    salaries_data = json.load(f)
    salaries = salaries_data.get('salaries', {})

OFFICIAL_LISTS_FILE = PUBLIC / 'official-occupation-lists.json'
if OFFICIAL_LISTS_FILE.exists():
    with open(OFFICIAL_LISTS_FILE) as f:
        official_lists = json.load(f)
    federal_csol = set(official_lists.get('federal', {}).get('CSOL_anzscos', []))
    state_lists = {
        s: {
            '190': set(info.get('190', [])),
            '491': set(info.get('491', [])),
            'scraped': info.get('scraped', False),
            'source': info.get('source', ''),
        }
        for s, info in official_lists.get('states', {}).items()
    }
    print(f"  Loaded official lists: federal CSOL = {len(federal_csol)} codes")
else:
    print("  WARN: official-occupation-lists.json missing — everything will be 'not_sponsored'")
    federal_csol = set()
    state_lists = {}

STATES = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'ACT', 'NT']
VISA_TYPES = ['190', '491', '482']

PATTERNS = {
    'manager': {'base_salary': 70000, 'exp': 2},
    'engineer': {'base_salary': 65000, 'exp': 2},
    'health': {'base_salary': 55000, 'exp': 1},
    'trade': {'base_salary': 60000, 'exp': 3},
    'ict': {'base_salary': 60000, 'exp': 1},
    'accountant': {'base_salary': 55000, 'exp': 1},
}


def classify_occupation(anzsco, name):
    nl = (name or '').lower()
    for pat, cfg in PATTERNS.items():
        if pat in nl:
            return cfg
    g = anzsco[0]
    if g == '1':
        return PATTERNS['manager']
    if g == '2':
        if any(x in nl for x in ('engineer', 'architect')):
            return PATTERNS['engineer']
        if any(x in nl for x in ('nurse', 'doctor', 'pharmacist', 'therapist', 'psychologist')):
            return PATTERNS['health']
        if any(x in nl for x in ('accountant', 'auditor')):
            return PATTERNS['accountant']
        if any(x in nl for x in ('software', 'programmer', 'developer', 'analyst')):
            return PATTERNS['ict']
    if g == '3':
        return PATTERNS['trade']
    return {'base_salary': None, 'exp': 1}


def get_salary(anzsco):
    """Real salary from JSA/source — None if unknown (NO synthetic fallback)."""
    if anzsco in salaries:
        s = salaries[anzsco].get('annualSalary')
        if s and s > 0:
            return int(s)
    return None


def is_on_list(anzsco, state, visa):
    if anzsco not in federal_csol:
        return False
    if visa == '482':
        return True  # SC 482 uses federal CSOL only — no state-specific list
    info = state_lists.get(state)
    if not info:
        return False
    return anzsco in info.get(visa, set())


VISA_LABEL = {
    '190': 'SC 190 Skilled Nominated',
    '491': 'SC 491 Skilled Work Regional',
    '482': 'SC 482 Skills in Demand',
}


def not_sponsored(visa, state, reason, source_url):
    msg = (
        "This occupation is NOT on the federal Combined Skilled Occupation List (CSOL) — SC 482 cannot be sponsored."
        if (visa == '482' and 'CSOL' in reason)
        else f"This occupation is NOT on the {state} nomination list for SC {visa}."
        if visa != '482'
        else "This occupation is NOT on the federal CSOL — SC 482 cannot be sponsored."
    )
    return {
        'visa': VISA_LABEL[visa],
        'status': 'not_sponsored',
        'onOfficialList': False,
        'reason': reason,
        'sourceUrl': source_url,
        'notes': [
            msg,
            "Verify against the official source before assuming ineligibility — lists are updated periodically.",
        ],
    }


def sponsored(visa, anzsco, occ_name, cfg, state, source_url, scraped):
    salary = get_salary(anzsco)
    has_salary = salary is not None

    if has_salary and cfg['base_salary'] is not None:
        base_min = max(cfg['base_salary'], int(salary * 0.7))
    elif has_salary:
        base_min = int(salary * 0.7)
    elif cfg['base_salary'] is not None:
        base_min = cfg['base_salary']
    else:
        base_min = None

    mults = {'NSW': 1.0, 'VIC': 0.98, 'QLD': 0.95, 'WA': 1.05,
             'SA': 0.90, 'TAS': 0.88, 'ACT': 1.02, 'NT': 1.08}
    mult = mults[state]
    exp = cfg['exp']

    common = {
        'onOfficialList': True,
        'status': 'sponsored',
        'sourceUrl': source_url,
        'sourceScraped': scraped,
        'salaryDataAvailable': has_salary,
    }

    if visa == '190':
        return {
            **common,
            'visa': VISA_LABEL['190'],
            'type': 'Permanent',
            'stream': 'Points-based + State nomination (mandatory)',
            'minSalary': int(base_min * mult) if base_min is not None else None,
            'minExperienceYears': exp,
            'minPoints': 65,
            'skillsAssessmentRequired': True,
            'jobOfferRequired': False,
            'residencyRequired': False,
            'stateSponsorship': 'Required (mandatory)',
            'notes': [
                "State nomination is REQUIRED — you cannot apply without it",
                f"Requires {exp}+ years relevant experience",
                "Minimum 65 points (state nomination adds 5 pts)",
                "Family can accompany on permanent visa",
                "Pathway to Australian citizenship (4 years residency)",
            ],
        }

    if visa == '491':
        return {
            **common,
            'visa': VISA_LABEL['491'],
            'type': 'Provisional (5 years)',
            'stream': 'Regional + Points-based + State nomination (mandatory)',
            'minSalary': int(base_min * mult * 0.85) if base_min is not None else None,
            'minExperienceYears': max(1, exp - 1),
            'minPoints': 55,
            'skillsAssessmentRequired': True,
            'jobOfferRequired': False,
            'residencyRequired': True,
            'stateSponsorship': 'Required (state or family sponsor)',
            'regionalRequirement': True,
            'notes': [
                "State nomination OR eligible family sponsor is REQUIRED",
                f"For regional areas of {state}",
                "5-year provisional visa (pathway to permanence)",
                "Must live/work in designated regional area",
                "Minimum 55 points",
                "Can apply for SC 191 permanent visa after 3 years regional living and working",
            ],
        }

    if visa == '482':
        sal = max(int((base_min or 0) * mult * 0.8), 73150)
        return {
            **common,
            'visa': VISA_LABEL['482'],
            'type': 'Temporary (1-4 years)',
            'stream': 'Employer-sponsored (mandatory)',
            'minSalary': sal,
            'minExperienceYears': max(0, exp - 2),
            'minPoints': None,
            'skillsAssessmentRequired': False,
            'jobOfferRequired': True,
            'residencyRequired': False,
            'stateSponsorship': 'Not applicable (employer-sponsored instead)',
            'employerRequired': True,
            'notes': [
                "Job offer from an approved sponsoring employer is REQUIRED",
                "Employer must be a Standard Business Sponsor or equivalent",
                "Minimum salary must meet TSMIT (AUD $73,150 from 1 Jul 2024)",
                "Temporary visa (1-4 years, extendable in some streams)",
                "PR pathway via SC 186 ENS after 2 years (varies by stream)",
            ],
        }
    return {}


print(f"\nGenerating for {len(all_occupations)} occupations × {len(STATES)} states × {len(VISA_TYPES)} visas …")

sponsored_count = not_sponsored_count = no_salary_count = 0

output = {
    'snapshotDate': datetime.now().strftime('%Y-%m-%d'),
    'lastUpdated': datetime.now().isoformat(),
    'source': 'Computed from public/official-occupation-lists.json + public/salaries.json',
    'schema': {
        'structure': 'requirements[anzsco][state][visa_type]',
        'visa_types': {
            '190': 'SC 190 Skilled Nominated (Permanent, state-nominated)',
            '491': 'SC 491 Skilled Work Regional (Provisional 5yr, state/family-nominated)',
            '482': 'SC 482 Skills in Demand (Temporary, employer-sponsored)',
        },
        'states': STATES,
        'entry_status_values': ['sponsored', 'not_sponsored'],
    },
    'requirements': {},
}

for anzsco, occ in all_occupations.items():
    name = occ.get('name', 'Unknown')
    cfg = classify_occupation(anzsco, name)
    if get_salary(anzsco) is None:
        no_salary_count += 1
    output['requirements'][anzsco] = {}
    for state in STATES:
        info = state_lists.get(state, {})
        src = info.get('source', '')
        scraped = info.get('scraped', False)
        per_visa = {}
        for visa in VISA_TYPES:
            if is_on_list(anzsco, state, visa):
                per_visa[visa] = sponsored(visa, anzsco, name, cfg, state, src, scraped)
                sponsored_count += 1
            else:
                if anzsco not in federal_csol:
                    reason = 'Not on federal Combined Skilled Occupation List (CSOL)'
                    s_url = 'https://immi.homeaffairs.gov.au/visas/working-in-australia/skill-occupation-list'
                else:
                    reason = f'Not on {state} nomination list for SC {visa}'
                    s_url = src
                per_visa[visa] = not_sponsored(visa, state, reason, s_url)
                not_sponsored_count += 1
        output['requirements'][anzsco][state] = per_visa

total = sponsored_count + not_sponsored_count
print(f"\nGenerated {total} combinations:")
print(f"  Sponsored:      {sponsored_count:>6}  ({sponsored_count*100//total}%)")
print(f"  Not sponsored:  {not_sponsored_count:>6}  ({not_sponsored_count*100//total}%)")
print(f"  Occupations w/o salary data: {no_salary_count}/{len(all_occupations)} ({no_salary_count*100//len(all_occupations)}%)")

out_path = PUBLIC / 'state-occupation-requirements.json'
with open(out_path, 'w') as f:
    json.dump(output, f, indent=2)
print(f"\nWrote {out_path.name} ({out_path.stat().st_size / (1024*1024):.1f} MB)")

print("\nSample (261312 Developer Programmer):")
sample = output['requirements'].get('261312', {})
for state in ['NSW', 'TAS', 'NT', 'VIC']:
    print(f"  {state}:")
    for visa in VISA_TYPES:
        e = sample.get(state, {}).get(visa, {})
        if e.get('status') == 'sponsored':
            sal = e.get('minSalary')
            sal_str = f"${sal:,}" if sal is not None else "N/A"
            print(f"    SC {visa}: sponsored  salary={sal_str}  exp={e.get('minExperienceYears')}y")
        else:
            print(f"    SC {visa}: {e.get('status')} — {e.get('reason')}")
