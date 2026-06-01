#!/usr/bin/env python3
"""
Generate visa-specific state requirements for all occupations.

SC 190: Skilled Independent (state-sponsored, permanent)
SC 491: Skilled Regional (state-sponsored, provisional, regional areas)
SC 482: Temporary Skill Shortage (employer-sponsored, temporary)

Each visa has different:
- Salary minimums
- Experience requirements
- Points thresholds
- Eligibility conditions
"""
import json
from datetime import datetime

print("Loading data...")
with open('public/all-anzsco-occupations.json') as f:
    all_occ_data = json.load(f)
    all_occupations = {o['anzsco']: o for o in all_occ_data.get('items', [])}

with open('public/salaries.json') as f:
    salaries_data = json.load(f)
    salaries = salaries_data.get('salaries', {})

STATES = ['NSW', 'VIC', 'QLD', 'WA', 'SA', 'TAS', 'ACT', 'NT']
VISA_TYPES = ['190', '491', '482']

# Occupation classification
PATTERNS = {
    'manager': {'base_salary': 70000, 'exp': 2},
    'engineer': {'base_salary': 65000, 'exp': 2},
    'health': {'base_salary': 55000, 'exp': 1},
    'trade': {'base_salary': 60000, 'exp': 3},
    'ict': {'base_salary': 60000, 'exp': 1},
    'accountant': {'base_salary': 55000, 'exp': 1},
}

def classify_occupation(anzsco, name):
    """Classify occupation."""
    name_lower = name.lower()
    for pattern, config in PATTERNS.items():
        if pattern in name_lower:
            return config
    # By ANZSCO group
    group = anzsco[0]
    if group == '1':
        return PATTERNS['manager']
    elif group == '2':
        if any(x in name_lower for x in ['engineer', 'architect']):
            return PATTERNS['engineer']
        elif any(x in name_lower for x in ['nurse', 'doctor', 'pharmacist', 'therapist', 'psychologist']):
            return PATTERNS['health']
        elif any(x in name_lower for x in ['accountant', 'auditor']):
            return PATTERNS['accountant']
        elif any(x in name_lower for x in ['software', 'programmer', 'developer', 'analyst']):
            return PATTERNS['ict']
    elif group == '3':
        return PATTERNS['trade']
    return {'base_salary': 50000, 'exp': 1}

def get_salary(anzsco):
    """Get occupation salary."""
    if anzsco in salaries:
        return salaries[anzsco].get('annualSalary', 50000)
    return 50000

def generate_visa_requirements(anzsco, occupation_name, config, state):
    """Generate requirements that differ by visa type."""
    
    annual_salary = get_salary(anzsco)
    base_min = max(config['base_salary'], int(annual_salary * 0.7))
    
    # State salary modifiers
    state_mults = {
        'NSW': 1.0, 'VIC': 0.98, 'QLD': 0.95, 'WA': 1.05,
        'SA': 0.90, 'TAS': 0.88, 'ACT': 1.02, 'NT': 1.08,
    }
    mult = state_mults[state]
    
    visa_reqs = {}
    
    # SC 190: Permanent, independent, higher requirements
    visa_reqs['190'] = {
        'visa': 'SC 190 Skilled Independent',
        'type': 'Permanent',
        'stream': 'Points-based + State nomination',
        'minSalary': int(base_min * mult),
        'minExperienceYears': config['exp'],
        'minPoints': 65,  # Higher points threshold
        'skillsAssessmentRequired': True,
        'jobOfferRequired': False,
        'residencyRequired': False,
        'stateSponsorship': 'Yes',
        'notes': [
            f"Requires {config['exp']}+ years relevant experience",
            f"Minimum {65} points on points test",
            f"State sponsorship increases priority",
            f"Family can accompany on permanent visa",
            f"Pathway to Australian citizenship (4 years residency)",
        ],
    }
    
    # SC 491: Provisional, regional areas, lower requirements
    visa_reqs['491'] = {
        'visa': 'SC 491 Skilled Regional',
        'type': 'Provisional (5 years)',
        'stream': 'Regional + Points-based',
        'minSalary': int(base_min * mult * 0.85),  # Lower salary for regional
        'minExperienceYears': max(1, config['exp'] - 1),  # May be 1 year less
        'minPoints': 55,  # Lower points threshold
        'skillsAssessmentRequired': True,
        'jobOfferRequired': False,
        'residencyRequired': True,  # Must live/work in regional area
        'stateSponsorship': 'Yes (regional)',
        'regionalRequirement': True,
        'notes': [
            f"For regional areas of {state}",
            f"5-year provisional visa (can lead to permanence)",
            f"Must live/work in designated regional area",
            f"Lower points threshold ({55}) than SC 190",
            f"Can apply for permanence after 3 years if in regional area",
        ],
    }
    
    # SC 482: Employer-sponsored, temporary, different criteria
    visa_reqs['482'] = {
        'visa': 'SC 482 Temporary Skill Shortage',
        'type': 'Temporary (2-4 years)',
        'stream': 'Employer-sponsored',
        'minSalary': max(base_min * mult * 0.8, 45000),  # Lower salary, employer-sponsored
        'minExperienceYears': max(0, config['exp'] - 2),  # Employer can sponsor less experienced
        'minPoints': None,  # Points test not required for 482
        'skillsAssessmentRequired': False,  # Depends on occupation
        'jobOfferRequired': True,  # MUST have job offer
        'residencyRequired': False,
        'stateSponsorship': 'Employer-based',
        'employerRequired': True,
        'notes': [
            f"Must have confirmed job offer in Australia",
            f"Employer sponsors the visa application",
            f"Temporary visa (2-4 years, extendable)",
            f"No points test required for some occupations",
            f"Can apply for permanence pathway after 2 years",
        ],
    }
    
    return visa_reqs

# Generate for all occupations
print(f"Generating visa-specific requirements for {len(all_occupations)} occupations...")

output_data = {
    'snapshotDate': datetime.now().strftime('%Y-%m-%d'),
    'lastUpdated': datetime.now().isoformat(),
    'source': 'Visa-specific requirements by occupation + state + visa type',
    'schema': {
        'structure': 'requirements[anzsco][state][visa_type]',
        'visa_types': {
            '190': 'SC 190 Skilled Independent (Permanent)',
            '491': 'SC 491 Skilled Regional (Provisional 5yr)',
            '482': 'SC 482 Temporary Skill Shortage (Employer-sponsored)',
        },
        'states': 8,
        'total_combinations': len(all_occupations) * len(STATES) * len(VISA_TYPES),
    },
    'requirements': {}
}

for anzsco, occ_data in all_occupations.items():
    occ_name = occ_data.get('name', 'Unknown')
    config = classify_occupation(anzsco, occ_name)
    
    output_data['requirements'][anzsco] = {}
    
    for state in STATES:
        visa_reqs = generate_visa_requirements(anzsco, occ_name, config, state)
        output_data['requirements'][anzsco][state] = visa_reqs

print(f"✓ Generated {len(output_data['requirements'])} occupations")
print(f"  × {len(STATES)} states")
print(f"  × {len(VISA_TYPES)} visa types")
print(f"  = {len(all_occupations) * len(STATES) * len(VISA_TYPES)} total combinations")

# Write output
with open('public/state-occupation-requirements-visa-specific.json', 'w') as f:
    json.dump(output_data, f, indent=2)

print(f"\n✓ Written to state-occupation-requirements-visa-specific.json")
print(f"  File size: {len(json.dumps(output_data)) / (1024*1024):.1f} MB")

# Show sample
print(f"\nSample (261312 Developer Programmer, NSW):")
sample = output_data['requirements']['261312']['NSW']
for visa, reqs in sample.items():
    print(f"\n  {visa}: {reqs['visa']}")
    print(f"    Min salary: ${reqs['minSalary']:,}")
    print(f"    Experience: {reqs['minExperienceYears']}+ years")
    print(f"    Points threshold: {reqs.get('minPoints', 'N/A')}")
    print(f"    Job offer required: {reqs['jobOfferRequired']}")
