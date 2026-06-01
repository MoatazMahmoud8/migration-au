#!/usr/bin/env python3
"""
Add Australian university graduate pathways as a SEPARATE reference,
not embedded in every requirement (which made file 36MB).

Structure:
- Top-level: graduatePathways[state] = full pathway details (stored ONCE)
- Each requirement: hasGraduatePathway: true/false (lightweight flag)
"""
import json
from datetime import datetime
import os

print("Loading existing state requirements...")
with open('public/state-occupation-requirements.json') as f:
    data = json.load(f)

GRADUATE_PATHWAYS = {
    'TAS': {
        'pathway_name': 'Tasmanian Graduate Stream',
        'universities': ['University of Tasmania (UTAS)'],
        'requirements': [
            'Completed CRICOS-registered course at UTAS',
            'Lived in Tasmania for at least 2 years during study',
            'Minimum 1-year course duration',
            'Within 2 years of graduation',
        ],
        'benefits': [
            'Lower salary requirement (-15%)',
            'Reduced experience requirement',
            'Priority processing',
            'Exclusive occupations available',
        ],
    },
    'SA': {
        'pathway_name': 'International Graduate of South Australia',
        'universities': [
            'University of Adelaide', 'Flinders University',
            'University of South Australia (UniSA)',
            'Carnegie Mellon University Adelaide', 'Torrens University',
        ],
        'requirements': [
            'Completed CRICOS course at SA institution',
            'Minimum 1 year duration of study',
            'Lived in SA during entire study period',
            'Within 3 years of graduation',
        ],
        'benefits': [
            'Exclusive Supplementary Skilled List access',
            'Lower salary threshold',
            'Easier nomination process',
        ],
    },
    'ACT': {
        'pathway_name': 'ACT Graduate / Canberra Resident',
        'universities': [
            'Australian National University (ANU)',
            'University of Canberra (UC)',
            'UNSW Canberra (ADFA)',
            'Australian Catholic University',
        ],
        'requirements': [
            'Completed CRICOS course at ACT institution',
            'Lived in Canberra during study',
            'Minimum 1 year of study in ACT',
        ],
        'benefits': [
            'Access to ACT Critical Skills List',
            'Lower salary requirement',
            'Faster processing through ACT matrix',
        ],
    },
    'NT': {
        'pathway_name': 'Northern Territory Graduate Stream',
        'universities': ['Charles Darwin University (CDU)'],
        'requirements': [
            'Completed CRICOS course at CDU',
            'Lived in NT for 2+ years',
            'Commitment to live in NT for 3 years post-visa',
        ],
        'benefits': [
            'Most flexible requirements in Australia',
            'Lower salary threshold',
            'Direct pathway to permanent residence',
        ],
    },
    'VIC': {
        'pathway_name': 'Victorian Skilled Migration (Research)',
        'universities': [
            'University of Melbourne', 'Monash University',
            'RMIT University', 'Deakin University',
            'La Trobe University', 'Swinburne University',
        ],
        'requirements': [
            'PhD from Victorian institution (for research occupations)',
            'OR Masters by research from Victorian uni',
            'Lived in Victoria during study',
        ],
        'benefits': [
            'Special pathway for researchers',
            'Lower salary threshold for academics',
            'Faster processing',
        ],
    },
    'WA': {
        'pathway_name': 'Western Australia Graduate Stream',
        'universities': [
            'University of Western Australia (UWA)',
            'Curtin University', 'Murdoch University',
            'Edith Cowan University (ECU)',
        ],
        'requirements': [
            'Completed CRICOS course at WA institution',
            'Lived in WA during study',
            'Minimum 2 years of study in WA',
        ],
        'benefits': [
            'Access to WA Graduate Stream',
            'Reduced salary requirements',
            'Special pathway for healthcare/STEM',
        ],
    },
    'QLD': {
        'pathway_name': 'Queensland Graduate Skilled Stream',
        'universities': [
            'University of Queensland (UQ)',
            'Queensland University of Technology (QUT)',
            'Griffith University', 'James Cook University (JCU)',
            'Bond University', 'Central Queensland University (CQU)',
        ],
        'requirements': [
            'Completed CRICOS course at QLD institution',
            'Lived in QLD during study',
            'Minimum 1 year of study',
        ],
        'benefits': [
            'Access to QLD Skilled Graduate Stream',
            'Lower salary thresholds',
            'Access to regional QLD opportunities',
        ],
    },
    'NSW': {
        'pathway_name': 'NSW Graduate / Resident Stream',
        'universities': [
            'University of Sydney', 'UNSW Sydney',
            'University of Technology Sydney (UTS)',
            'Macquarie University', 'Western Sydney University',
            'University of Newcastle', 'University of Wollongong',
        ],
        'requirements': [
            'Lived in NSW for 1+ year',
            'OR studied at NSW institution',
            'OR worked in NSW',
        ],
        'benefits': [
            'NSW Skills List Stream 2 (Living in NSW)',
            'Wider occupation eligibility',
            'Lower experience requirements',
        ],
    },
}

print("Cleaning previous embedded pathway data + adding lightweight flags...")
cleaned_count = 0
flagged_count = 0
for anzsco, state_data in data['requirements'].items():
    for state, visa_data in state_data.items():
        for visa_type, req in visa_data.items():
            if 'australianGraduatePathway' in req:
                del req['australianGraduatePathway']
                cleaned_count += 1
            req['hasGraduatePathway'] = state in GRADUATE_PATHWAYS
            flagged_count += 1
            # Add Australian graduate option note
            au_note = f"🎓 Graduate of {state} university: easier pathway available"
            if 'notes' in req and au_note not in req['notes']:
                # Remove old version if any (cleanup)
                req['notes'] = [n for n in req['notes'] if 'Australian graduate' not in n]
                req['notes'] = [au_note] + req['notes']

print(f"✓ Cleaned {cleaned_count} embedded entries")
print(f"✓ Flagged {flagged_count} requirements with hasGraduatePathway")

data['graduatePathways'] = GRADUATE_PATHWAYS
data['lastUpdated'] = datetime.now().isoformat()
data['snapshotDate'] = datetime.now().strftime('%Y-%m-%d')

if 'schema' not in data:
    data['schema'] = {}
data['schema']['graduatePathways'] = {
    'description': 'Top-level reference: graduatePathways[state] = pathway details',
    'note': 'Each requirement has hasGraduatePathway flag (true/false)',
    'states_with_pathway': list(GRADUATE_PATHWAYS.keys()),
}

print("\nWriting compact data...")
with open('public/state-occupation-requirements.json', 'w') as f:
    json.dump(data, f, indent=2)

size_mb = os.path.getsize('public/state-occupation-requirements.json') / (1024 * 1024)
print(f"✓ File size: {size_mb:.1f} MB")

print(f"\n{'='*60}")
print("✅ AUSTRALIAN GRADUATE PATHWAYS ADDED")
print('='*60)
print(f"\n📍 All 8 states have graduate pathways!")
print(f"📚 Total universities: {sum(len(p['universities']) for p in GRADUATE_PATHWAYS.values())}")
for state, info in GRADUATE_PATHWAYS.items():
    print(f"\n   {state}: {len(info['universities'])} unis - {info['pathway_name']}")
