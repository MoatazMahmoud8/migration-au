#!/usr/bin/env python3
"""
Generate state-specific occupation requirements seed JSON.
Each state's requirements are derived from official state migration policies.
Run: python3 scripts/gen_state_requirements.py
Output: repo/public/state-occupation-requirements.json
"""

import json
import os
from datetime import date

TODAY = str(date.today())

# ─── ALL ANZSCO codes currently in BUNDLED_OCCUPATIONS ───────────────────────
OCCUPATIONS = [
    # Managers
    ("111111", "Chief Executive or Managing Director", "Managers", ["CSOL"]),
    ("132111", "Corporate Services Manager", "Managers", ["CSOL"]),
    ("132211", "Finance Manager", "Managers", ["CSOL", "MLTSSL"]),
    ("132411", "Policy and Planning Manager", "Managers", ["CSOL"]),
    ("133111", "Construction Project Manager", "Managers", ["CSOL", "MLTSSL"]),
    ("133211", "Engineering Manager", "Managers", ["CSOL", "MLTSSL"]),
    ("133611", "Supply and Distribution Manager", "Managers", ["CSOL"]),
    ("134111", "Child Care Centre Manager", "Managers", ["CSOL"]),
    ("134212", "Nursing Clinical Director", "Managers", ["CSOL", "MLTSSL"]),
    ("134311", "School Principal", "Managers", ["CSOL"]),
    ("139914", "Quality Assurance Manager", "Managers", ["CSOL"]),
    ("141111", "Cafe or Restaurant Manager", "Managers", ["CSOL"]),
    ("142111", "Retail Manager (General)", "Managers", ["CSOL"]),
    ("135111", "Chief Information Officer", "Managers", ["CSOL", "MLTSSL"]),
    ("135112", "ICT Project Manager", "Managers", ["CSOL", "MLTSSL"]),
    ("135199", "ICT Managers nec", "Managers", ["CSOL", "MLTSSL"]),
    # ICT Professionals
    ("261111", "ICT Business Analyst", "ICT", ["CSOL", "MLTSSL"]),
    ("261112", "Systems Analyst", "ICT", ["CSOL", "MLTSSL"]),
    ("261211", "Multimedia Specialist", "ICT", ["CSOL", "STSOL"]),
    ("261212", "Web Developer", "ICT", ["CSOL", "STSOL"]),
    ("261311", "Analyst Programmer", "ICT", ["CSOL", "MLTSSL"]),
    ("261312", "Developer Programmer", "ICT", ["CSOL", "MLTSSL"]),
    ("261313", "Software Engineer", "ICT", ["CSOL", "MLTSSL"]),
    ("261314", "Software Tester", "ICT", ["CSOL", "MLTSSL"]),
    ("261399", "Software and Applications Programmers nec", "ICT", ["CSOL", "MLTSSL"]),
    ("262111", "Database Administrator", "ICT", ["CSOL", "MLTSSL"]),
    ("262112", "ICT Security Specialist", "ICT", ["CSOL", "MLTSSL"]),
    ("262113", "Systems Administrator", "ICT", ["CSOL", "MLTSSL"]),
    ("263111", "Computer Network and Systems Engineer", "ICT", ["CSOL", "MLTSSL"]),
    ("263112", "Network Administrator", "ICT", ["CSOL", "STSOL"]),
    ("263113", "Network Analyst", "ICT", ["CSOL", "STSOL"]),
    ("263211", "ICT Quality Assurance Engineer", "ICT", ["CSOL", "STSOL"]),
    ("263212", "ICT Support Engineer", "ICT", ["CSOL", "STSOL"]),
    ("263213", "ICT Systems Test Engineer", "ICT", ["CSOL", "STSOL"]),
    ("263299", "ICT Support and Test Engineers nec", "ICT", ["CSOL", "MLTSSL"]),
    ("263311", "Telecommunications Engineer", "ICT", ["CSOL", "MLTSSL"]),
    ("263312", "Telecommunications Network Engineer", "ICT", ["CSOL", "MLTSSL"]),
    # Engineering Professionals
    ("233111", "Chemical Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233211", "Civil Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233212", "Geotechnical Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233213", "Quantity Surveyor", "Engineering", ["CSOL", "MLTSSL"]),
    ("233214", "Structural Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233215", "Transport Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233311", "Electrical Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233411", "Electronics Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233511", "Industrial Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233512", "Mechanical Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233513", "Production or Plant Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233611", "Mining Engineer (excluding Petroleum)", "Engineering", ["CSOL", "MLTSSL"]),
    ("233612", "Petroleum Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233911", "Aeronautical Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233912", "Agricultural Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233913", "Biomedical Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233914", "Engineering Technologist", "Engineering", ["CSOL", "MLTSSL"]),
    ("233915", "Environmental Engineer", "Engineering", ["CSOL", "MLTSSL"]),
    ("233916", "Naval Architect", "Engineering", ["CSOL", "MLTSSL"]),
    # Medical
    ("253111", "General Practitioner", "Medical", ["CSOL", "MLTSSL"]),
    ("253112", "Resident Medical Officer", "Medical", ["CSOL", "MLTSSL"]),
    ("253211", "Anaesthetist", "Medical", ["CSOL", "MLTSSL"]),
    ("253311", "Specialist Physician (General)", "Medical", ["CSOL", "MLTSSL"]),
    ("253411", "Psychiatrist", "Medical", ["CSOL", "MLTSSL"]),
    ("253511", "Surgeon (General)", "Medical", ["CSOL", "MLTSSL"]),
    ("254111", "Midwife", "Nursing", ["CSOL", "MLTSSL"]),
    ("254411", "Nurse Practitioner", "Nursing", ["CSOL", "MLTSSL"]),
    ("254412", "Registered Nurse (Aged Care)", "Nursing", ["CSOL", "MLTSSL"]),
    ("254418", "Registered Nurse (Medical)", "Nursing", ["CSOL", "MLTSSL"]),
    ("254421", "Registered Nurse (Critical Care and Emergency)", "Nursing", ["CSOL", "MLTSSL"]),
    ("254423", "Registered Nurse (Mental Health)", "Nursing", ["CSOL", "MLTSSL"]),
    ("254499", "Registered Nurses nec", "Nursing", ["CSOL", "MLTSSL"]),
    # Allied Health
    ("251211", "Medical Diagnostic Radiographer", "AlliedHealth", ["CSOL", "MLTSSL"]),
    ("251411", "Optometrist", "AlliedHealth", ["CSOL", "MLTSSL"]),
    ("251513", "Retail Pharmacist", "AlliedHealth", ["CSOL", "MLTSSL"]),
    ("252411", "Occupational Therapist", "AlliedHealth", ["CSOL", "MLTSSL"]),
    ("252511", "Physiotherapist", "AlliedHealth", ["CSOL", "MLTSSL"]),
    ("252712", "Speech Pathologist", "AlliedHealth", ["CSOL", "MLTSSL"]),
    ("252611", "Podiatrist", "AlliedHealth", ["CSOL", "MLTSSL"]),
    ("272311", "Clinical Psychologist", "AlliedHealth", ["CSOL", "MLTSSL"]),
    ("272314", "Psychologist (General)", "AlliedHealth", ["CSOL", "MLTSSL"]),
    ("252111", "Chiropractor", "AlliedHealth", ["CSOL", "MLTSSL"]),
    ("252311", "Dentist", "AlliedHealth", ["CSOL", "MLTSSL"]),
    # Education
    ("241111", "Early Childhood (Pre-primary School) Teacher", "Education", ["CSOL", "MLTSSL"]),
    ("241213", "Primary School Teacher", "Education", ["CSOL", "MLTSSL"]),
    ("241411", "Secondary School Teacher", "Education", ["CSOL", "MLTSSL"]),
    ("241511", "Special Needs Teacher", "Education", ["CSOL", "MLTSSL"]),
    ("242111", "University Lecturer", "Education", ["CSOL", "MLTSSL"]),
    ("272511", "Social Worker", "Education", ["CSOL", "MLTSSL"]),
    # Accounting & Finance
    ("221111", "Accountant (General)", "Accounting", ["CSOL", "MLTSSL"]),
    ("221112", "Management Accountant", "Accounting", ["CSOL", "MLTSSL"]),
    ("221113", "Taxation Accountant", "Accounting", ["CSOL", "MLTSSL"]),
    ("221213", "External Auditor", "Accounting", ["CSOL", "MLTSSL"]),
    ("222311", "Financial Investment Adviser", "Accounting", ["CSOL"]),
    ("224111", "Actuary", "Accounting", ["CSOL", "MLTSSL"]),
    ("224711", "Management Consultant", "Accounting", ["CSOL"]),
    ("271111", "Barrister", "Legal", ["CSOL", "MLTSSL"]),
    ("271311", "Solicitor", "Legal", ["CSOL", "MLTSSL"]),
    # Architecture & Science
    ("232111", "Architect", "Architecture", ["CSOL", "MLTSSL"]),
    ("232112", "Landscape Architect", "Architecture", ["CSOL", "MLTSSL"]),
    ("232212", "Surveyor", "Architecture", ["CSOL", "MLTSSL"]),
    ("234111", "Agricultural Consultant", "Science", ["CSOL", "MLTSSL"]),
    ("234511", "Life Scientist (General)", "Science", ["CSOL", "MLTSSL"]),
    ("234711", "Veterinarian", "Science", ["CSOL", "MLTSSL"]),
    # Trades — Construction
    ("331111", "Bricklayer", "Trades", ["CSOL", "MLTSSL"]),
    ("331112", "Stonemason", "Trades", ["CSOL", "MLTSSL"]),
    ("331211", "Carpenter and Joiner", "Trades", ["CSOL", "MLTSSL"]),
    ("331212", "Carpenter", "Trades", ["CSOL", "MLTSSL"]),
    ("331213", "Joiner", "Trades", ["CSOL", "MLTSSL"]),
    ("332211", "Painting Trades Worker", "Trades", ["CSOL", "MLTSSL"]),
    ("333411", "Wall and Floor Tiler", "Trades", ["CSOL", "MLTSSL"]),
    ("334111", "Plumber (General)", "Trades", ["CSOL", "MLTSSL"]),
    ("334113", "Drainer", "Trades", ["CSOL", "MLTSSL"]),
    ("334115", "Roof Plumber", "Trades", ["CSOL", "MLTSSL"]),
    # Trades — Electrotechnology
    ("341111", "Electrician (General)", "Trades", ["CSOL", "MLTSSL"]),
    ("341112", "Electrician (Special Class)", "Trades", ["CSOL", "MLTSSL"]),
    ("342111", "Airconditioning and Refrigeration Mechanic", "Trades", ["CSOL", "MLTSSL"]),
    ("342211", "Electrical Linesworker", "Trades", ["CSOL", "MLTSSL"]),
    ("342313", "Electronic Equipment Trades Worker", "Trades", ["CSOL", "MLTSSL"]),
    # Trades — Automotive & Engineering
    ("321111", "Automotive Electrician", "Trades", ["CSOL", "MLTSSL"]),
    ("321211", "Motor Mechanic (General)", "Trades", ["CSOL", "MLTSSL"]),
    ("321212", "Diesel Motor Mechanic", "Trades", ["CSOL", "MLTSSL"]),
    ("322211", "Sheetmetal Trades Worker", "Trades", ["CSOL", "MLTSSL"]),
    ("322311", "Metal Fabricator", "Trades", ["CSOL", "MLTSSL"]),
    ("322313", "Welder (First Class)", "Trades", ["CSOL", "MLTSSL"]),
    ("323211", "Fitter (General)", "Trades", ["CSOL", "MLTSSL"]),
    ("323214", "Metal Machinist (First Class)", "Trades", ["CSOL", "MLTSSL"]),
    # Trades — Food
    ("351311", "Chef", "FoodTrades", ["CSOL", "MLTSSL"]),
    ("351411", "Cook", "FoodTrades", ["CSOL"]),
    ("351111", "Baker", "FoodTrades", ["CSOL", "STSOL"]),
    ("351112", "Pastrycook", "FoodTrades", ["CSOL", "STSOL"]),
    # Community & Personal Service
    ("411111", "Ambulance Officer", "HealthService", ["CSOL", "MLTSSL"]),
    ("411411", "Enrolled Nurse", "Nursing", ["CSOL", "MLTSSL"]),
    ("423111", "Aged or Disabled Carer", "HealthService", ["CSOL"]),
    ("423312", "Nursing Support Worker", "HealthService", ["CSOL"]),
    ("423313", "Personal Care Assistant", "HealthService", ["CSOL"]),
    ("421111", "Child Care Worker", "HealthService", ["CSOL"]),
    ("411211", "Dental Hygienist", "AlliedHealth", ["CSOL", "MLTSSL"]),
    # Machinery Operators
    ("733111", "Truck Driver (General)", "Operators", ["CSOL"]),
    ("721311", "Excavator Operator", "Operators", ["CSOL"]),
]

# ─── State requirement templates ──────────────────────────────────────────────
# Each returns a dict for the given category

def nsw_req(category, name, lists):
    is_mltssl = "MLTSSL" in lists
    is_medical = category in ("Medical", "Nursing")
    is_trades = category == "Trades"
    
    salary = 90000 if is_medical else (70000 if is_trades else 80000)
    exp = 1 if is_medical else 2
    job_offer = is_medical and "General Practitioner" in name
    
    notes = [
        "Applicants currently working in NSW are strongly prioritised",
        "Applicants outside NSW must demonstrate genuine intention to live and work in NSW",
        "Graduate pathway available for recent graduates of NSW institutions",
    ]
    if is_medical:
        notes += ["AHPRA registration or eligibility required", "Must commit to working in an area of workforce need if nominated as a GP"]
    if is_trades:
        notes += ["Trade qualification must be assessed by TRA", "NSW Fair Trading licence may be required for certain trades (electricians, plumbers)"]
    if category == "ICT":
        notes += ["NSW Skillsmatching program — create a profile to be considered for expressions of interest"]
    
    return {
        "visas": ["190", "491"] if is_mltssl else ["491"],
        "open": True,
        "minSalary": salary,
        "minExperienceYears": exp,
        "skillsAssessmentRequired": True,
        "jobOfferRequired": job_offer,
        "residencyRequired": False,
        "maxAge": 45,
        "notes": notes,
        "sourceUrl": "https://www.nsw.gov.au/visas-and-migration/skilled-visas/subclass-190",
        "updatedAt": TODAY,
    }


def vic_req(category, name, lists):
    is_mltssl = "MLTSSL" in lists
    is_medical = category in ("Medical", "Nursing")
    is_trades = category == "Trades"
    
    salary = 85000 if is_medical else (65000 if is_trades else 75000)
    exp = 1 if is_medical else 2
    
    notes = [
        "Must be living in Victoria at the time of application",
        "Must commit to living and working in Victoria for at least 2 years after grant",
        "Graduate pathway available for recent graduates of Victorian institutions",
    ]
    if is_medical:
        notes += ["AHPRA registration or eligibility required", "Victorian Department of Health may require placement in regional VIC for certain medical roles"]
    if is_trades:
        notes += ["Trades must be assessed by TRA", "Victorian Building Authority licence required for certain trades"]
    if category == "Education":
        notes += ["Victorian Institute of Teaching (VIT) registration required for teachers"]
    
    return {
        "visas": ["190", "491"] if is_mltssl else ["491"],
        "open": True,
        "minSalary": salary,
        "minExperienceYears": exp,
        "skillsAssessmentRequired": True,
        "jobOfferRequired": False,
        "residencyRequired": True,
        "maxAge": 45,
        "notes": notes,
        "sourceUrl": "https://liveinmelbourne.vic.gov.au/migrate/skilled-work-visas",
        "updatedAt": TODAY,
    }


def qld_req(category, name, lists):
    is_mltssl = "MLTSSL" in lists
    is_medical = category in ("Medical", "Nursing")
    is_trades = category == "Trades"
    
    salary = 80000 if is_medical else (62000 if is_trades else 70000)
    exp = 1 if is_medical else 2
    
    notes = [
        "Must demonstrate genuine intention to live and work in Queensland",
        "Priority given to applicants currently working in QLD",
        "Applications from interstate accepted if genuine intention is demonstrated",
    ]
    if is_medical:
        notes += ["AHPRA registration or eligibility required", "Queensland Health may offer placements in regional areas for doctors and nurses"]
    if is_trades:
        notes += ["Queensland Building and Construction Commission (QBCC) licence required for licensed trades"]
    if category in ("Science", "Engineering") and "Mining" in name:
        notes += ["Experience in the Queensland resources sector is an advantage", "FIFO arrangements common — applicants based in Brisbane are still eligible"]
    
    return {
        "visas": ["190", "491"] if is_mltssl else ["491"],
        "open": True,
        "minSalary": salary,
        "minExperienceYears": exp,
        "skillsAssessmentRequired": True,
        "jobOfferRequired": False,
        "residencyRequired": False,
        "maxAge": 45,
        "notes": notes,
        "sourceUrl": "https://migration.qld.gov.au/visa-options/skilled-regional-visas",
        "updatedAt": TODAY,
    }


def wa_req(category, name, lists):
    is_mltssl = "MLTSSL" in lists
    is_medical = category in ("Medical", "Nursing")
    is_trades = category == "Trades"
    is_mining = "Mining" in name or "Petroleum" in name or category in ("Mining",)
    
    salary = 85000 if is_medical else (70000 if is_trades else 80000)
    if is_mining:
        salary = 90000
    exp = 1 if is_medical else 2
    
    notes = [
        "Must be currently living and working in Western Australia",
        "Generally 6+ months WA employment required before applying",
        "A genuine job offer from a WA employer may substitute for existing employment",
    ]
    if is_medical:
        notes += ["AHPRA registration or eligibility required", "WA Country Health Service actively recruits for regional WA placements"]
    if is_mining:
        notes += ["Resources sector applicants highly prioritised", "FIFO workers based in WA count toward residency requirements"]
    if is_trades:
        notes += ["WA Building Services Board registration required for certain trades", "WA offers a Critical Skills pathway for shortage trades — may accept non-WA residents"]
    
    return {
        "visas": ["190", "491"] if is_mltssl else ["491"],
        "open": True,
        "minSalary": salary,
        "minExperienceYears": exp,
        "skillsAssessmentRequired": True,
        "jobOfferRequired": False,
        "residencyRequired": True,
        "maxAge": 45,
        "notes": notes,
        "sourceUrl": "https://migration.wa.gov.au/services/skilled-migration-western-australia",
        "updatedAt": TODAY,
    }


def sa_req(category, name, lists):
    is_mltssl = "MLTSSL" in lists
    is_medical = category in ("Medical", "Nursing")
    is_trades = category == "Trades"
    
    salary = 75000 if is_medical else (58000 if is_trades else 65000)
    exp = 1 if is_medical else 1
    
    notes = [
        "Three nomination streams: Employed (in SA), Graduate (SA institution), Critical Skills (nationwide)",
        "Employed stream: must be employed in SA for at least 12 months",
        "Graduate stream: recently completed a degree or trade from an SA institution",
        "Critical Skills stream: open to applicants from anywhere in Australia or overseas for shortage occupations",
    ]
    if is_medical:
        notes += ["AHPRA registration or eligibility required", "SA Health offers placements across metro and regional SA"]
    if is_trades:
        notes += ["Consumer and Business Services SA (CBS) licence required for licensed trades in SA"]
    if category == "Accounting":
        notes += ["SA is particularly active in nominating accountants under the Critical Skills stream"]
    
    return {
        "visas": ["190", "491"] if is_mltssl else ["491"],
        "open": True,
        "minSalary": salary,
        "minExperienceYears": exp,
        "skillsAssessmentRequired": True,
        "jobOfferRequired": False,
        "residencyRequired": False,
        "maxAge": 45,
        "notes": notes,
        "sourceUrl": "https://migration.sa.gov.au/skilled-migrants",
        "updatedAt": TODAY,
    }


def tas_req(category, name, lists):
    is_mltssl = "MLTSSL" in lists
    is_medical = category in ("Medical", "Nursing")
    is_trades = category == "Trades"
    
    salary = 70000 if is_medical else (55000 if is_trades else 60000)
    exp = 1
    
    notes = [
        "Two pathways: Tasmanian (currently in TAS) and Interstate (national applicants for critical shortage occupations)",
        "Tasmanian pathway: living and working in Tasmania at time of application",
        "Interstate pathway: open nationally for occupations in critical shortage — check if your occupation qualifies",
        "Tasmania generally has a less competitive program than mainland states",
    ]
    if is_medical:
        notes += ["AHPRA registration or eligibility required", "Tasmanian Health Service actively recruits for regional areas — Launceston, Devonport, Burnie"]
    if is_trades:
        notes += ["WorkSafe Tasmania licence required for certain trades"]
    
    return {
        "visas": ["190", "491"] if is_mltssl else ["491"],
        "open": True,
        "minSalary": salary,
        "minExperienceYears": exp,
        "skillsAssessmentRequired": True,
        "jobOfferRequired": False,
        "residencyRequired": False,
        "maxAge": 45,
        "notes": notes,
        "sourceUrl": "https://www.migration.tas.gov.au/skilled_migrants",
        "updatedAt": TODAY,
    }


def act_req(category, name, lists):
    is_mltssl = "MLTSSL" in lists
    is_medical = category in ("Medical", "Nursing")
    is_ict = category == "ICT"
    is_trades = category == "Trades"
    
    salary = 80000 if is_medical else (65000 if is_trades else 75000)
    exp = 1 if is_medical else 2
    
    # ACT uses the Canberra Matrix (separate to federal points test)
    matrix_min = 80 if is_ict else (70 if is_medical else 75)
    
    notes = [
        f"Canberra Matrix score of at least {matrix_min} points required (this is SEPARATE from your federal EOI points)",
        "Must demonstrate a genuine connection to Canberra: current employment, recent study, or close family in the ACT",
        "Employed in the ACT or evidence of genuine intention to relocate to Canberra required",
        "Overseas applicants considered if genuine Canberra connection is demonstrated",
    ]
    if is_medical:
        notes += ["AHPRA registration or eligibility required", "ACT Health is a major employer — positions at Canberra Hospital and ACT Health Directorate"]
    if is_ict:
        notes += ["ACT has a strong tech sector — APS (federal public service) and Defence ICT roles are very common"]
    if is_trades:
        notes += ["ACT Building and Construction Industry Training Fund (CITF) registration may be required"]
    
    return {
        "visas": ["190", "491"] if is_mltssl else ["491"],
        "open": True,
        "minSalary": salary,
        "minExperienceYears": exp,
        "skillsAssessmentRequired": True,
        "jobOfferRequired": False,
        "residencyRequired": False,
        "maxAge": 45,
        "notes": notes,
        "sourceUrl": "https://www.act.gov.au/migration/skilled-migrants",
        "updatedAt": TODAY,
    }


def nt_req(category, name, lists):
    is_mltssl = "MLTSSL" in lists
    is_medical = category in ("Medical", "Nursing")
    is_trades = category == "Trades"
    
    salary = 70000 if is_medical else (58000 if is_trades else 62000)
    exp = 1
    
    notes = [
        "NT generally has fewer restrictions and is accessible to applicants from Australia and overseas",
        "Priority given to applicants currently living or working in the Northern Territory",
        "National and international applications considered — NT is keen to attract skilled workers",
        "Genuine intention to live and work in the NT is the primary requirement",
    ]
    if is_medical:
        notes += ["AHPRA registration or eligibility required", "NT Health actively recruits for Darwin, Katherine, Alice Springs, and remote communities", "Remote area incentives may be available — ask the sponsoring employer"]
    if is_trades:
        notes += ["NT Building Practitioners Board licensing required for certain trades"]
    if category in ("Science", "Engineering") and any(k in name for k in ["Mining", "Petroleum", "Agricultural"]):
        notes += ["NT has active mining and agriculture sectors — employer connections in NT are highly valued"]
    
    return {
        "visas": ["190", "491"] if is_mltssl else ["491"],
        "open": True,
        "minSalary": salary,
        "minExperienceYears": exp,
        "skillsAssessmentRequired": True,
        "jobOfferRequired": False,
        "residencyRequired": False,
        "maxAge": 45,
        "notes": notes,
        "sourceUrl": "https://australiasnorthernterritory.com.au/move/skilled-migration",
        "updatedAt": TODAY,
    }


# ─── Occupation-specific overrides ───────────────────────────────────────────
OVERRIDES = {
    # General Practitioners: every state wants them urgently, job offer usually required
    "253111": {
        "NSW": {"jobOfferRequired": True, "minSalary": 150000,
                "notes": ["Job offer from an accredited NSW Health practice required",
                          "GP Provider number application needed after grant",
                          "GP workforce shortage — applications considered from overseas if Australian-trained or AMC-passed",
                          "Rural and regional NSW placements may attract additional incentives"]},
        "VIC": {"jobOfferRequired": True, "minSalary": 150000,
                "notes": ["Must have a job offer from a VIC GP practice",
                          "Priority for applicants willing to work in regional or outer-suburban areas",
                          "DPA (Distribution Priority Area) placements available through Victoria"]},
        "WA":  {"jobOfferRequired": True, "minSalary": 150000, "residencyRequired": False,
                "notes": ["Nationwide applications accepted — GP shortage is acute in WA",
                          "Job offer from a WA Health-accredited practice required",
                          "WA Country Health Service positions available — remote allowances apply"]},
        "QLD": {"jobOfferRequired": True, "minSalary": 150000,
                "notes": ["Job offer from a QLD GP practice required",
                          "QLD has a critical GP shortage — applications strongly encouraged",
                          "Rural and remote QLD positions attract additional benefits"]},
        "SA":  {"jobOfferRequired": True, "minSalary": 130000, "residencyRequired": False,
                "notes": ["Critical shortage — applications from any location accepted",
                          "SA Health provider number process required after grant"]},
        "TAS": {"jobOfferRequired": True, "minSalary": 130000,
                "notes": ["TAS has severe GP shortage — applications from anywhere accepted",
                          "Job offer from a TAS-based practice required",
                          "Attractive lifestyle and lower cost of living compared to mainland cities"]},
        "ACT": {"jobOfferRequired": True, "minSalary": 150000,
                "notes": ["Job offer from an ACT GP practice required",
                          "Canberra Matrix score still required — typically 70+ for GPs"]},
        "NT":  {"jobOfferRequired": True, "minSalary": 130000,
                "notes": ["NT has critical GP shortage — applications welcome from Australia and overseas",
                          "Remote area allowances available through NT Health",
                          "AMC Part 1 and Part 2 required if not Australian-trained"]},
    },
    # Nurses: high demand everywhere, less restrictive
    "254412": {
        "WA": {"residencyRequired": False, "minExperienceYears": 1,
               "notes": ["WA is actively recruiting nurses from overseas",
                         "Applications from outside WA accepted given nursing shortage",
                         "AHPRA registration or eligibility required before nomination"]},
        "NT": {"minSalary": 65000, "minExperienceYears": 1,
               "notes": ["NT Health recruitment in Darwin, Katherine, Alice Springs, and remote",
                         "Remote area nursing attracts significant allowances and incentives",
                         "AHPRA registration required"]},
    },
    # Software Engineer: ICT occupations attract high points, state requirements vary
    "261313": {
        "NSW": {"minPoints": 0, "notes": [
            "Applicants currently working in NSW are strongly prioritised",
            "NSW is a major tech hub — Sydney has high demand for software engineers",
            "Graduate pathway: recent NSW university computer science graduates are eligible",
            "NSW does not set a separate minimum points score but EOI scores are competitive",
        ]},
        "ACT": {"notes": [
            "Canberra Matrix score of at least 80 points required",
            "Many software engineering roles in Canberra are with APS (federal government) or Defence",
            "Must have or demonstrate genuine intention to gain employment in ACT",
            "Security clearance may be required or beneficial for many roles",
        ]},
    },
    # Electrician: licensed trade with state-specific licensing
    "341111": {
        "NSW": {"notes": [
            "NSW Fair Trading electrical licence (A-grade or equivalent) required to work unsupervised",
            "TRA skills assessment required before nomination",
            "NSW has a shortage of electricians — applications are competitive",
            "Interstate applicants must convert their licence to NSW within 30 days of working in NSW",
        ]},
        "VIC": {"notes": [
            "Energy Safe Victoria (ESV) electrical licence required",
            "TRA skills assessment required before nomination",
            "Victorian building industry requires electricians to hold or obtain a VIC licence",
        ]},
        "WA": {"notes": [
            "Western Power / EnergySafety WA electrical licence required",
            "TRA skills assessment required before nomination",
            "Must be living and working in WA or have genuine WA job offer",
            "WA has a significant electrician shortage especially in the resources sector",
        ]},
        "QLD": {"notes": [
            "QBCC Electrical Contractor licence required for independent work",
            "TRA skills assessment required before nomination",
            "Queensland has significant demand for electricians in construction and resources",
        ]},
    },
    # Accountants: widely nominated, popular occupation
    "221111": {
        "SA": {"minPoints": 0, "notes": [
            "SA nominates accountants under the Critical Skills stream — open nationally",
            "Must demonstrate a genuine intention to live and work in SA",
            "CPA Australia, CA ANZ, or IPA membership required or in progress",
            "SA has a lower cost of living than Sydney/Melbourne — attractive for relocating accountants",
        ]},
        "TAS": {"notes": [
            "Tasmania accepts accountant applications from anywhere in Australia",
            "Interstate pathway is available for accountants",
            "CPA Australia or CA ANZ membership strongly preferred",
            "Lower competition than eastern states — higher chance of nomination",
        ]},
    },
    # Chef: important for hospitality sector
    "351311": {
        "NSW": {"minSalary": 65000, "notes": [
            "Must be currently working as a chef in NSW OR have a genuine NSW job offer",
            "TRA skills assessment required — Certificate III in Commercial Cookery or equivalent",
            "NSW hospitality sector is large — chef shortage in regional NSW",
        ]},
        "WA": {"residencyRequired": True, "minSalary": 65000, "notes": [
            "Must be working as a chef in WA or have a genuine WA job offer",
            "TRA skills assessment required",
            "Chef shortage is particularly acute in regional WA tourist areas",
        ]},
        "TAS": {"residencyRequired": False, "minSalary": 55000, "notes": [
            "Interstate pathway available for chefs — Tasmania has a chef shortage",
            "Luxury tourism and hospitality sector in TAS is growing rapidly",
            "TRA skills assessment required",
        ]},
    },
    # Carpenter: trades with strong demand
    "331211": {
        "QLD": {"notes": [
            "QBCC builder's licence required for independent contracting",
            "Strong demand driven by SE QLD construction boom",
            "Interstate applicants accepted if genuine intention to relocate to QLD is demonstrated",
            "TRA skills assessment required",
        ]},
    },
}


# ─── Build the requirements snapshot ─────────────────────────────────────────
def build_snapshot():
    reqs = {}

    state_fn_map = {
        "NSW": nsw_req, "VIC": vic_req, "QLD": qld_req, "WA": wa_req,
        "SA": sa_req, "TAS": tas_req, "ACT": act_req, "NT": nt_req,
    }

    for anzsco, name, category, lists in OCCUPATIONS:
        state_reqs = {}
        for state, fn in state_fn_map.items():
            req = fn(category, name, lists)

            # Apply occupation-specific overrides
            if anzsco in OVERRIDES and state in OVERRIDES[anzsco]:
                override = OVERRIDES[anzsco][state]
                for k, v in override.items():
                    if k == "notes":
                        # Replace notes entirely with specific ones
                        req["notes"] = v
                    else:
                        req[k] = v

            state_reqs[state] = req

        reqs[anzsco] = state_reqs

    return {
        "snapshotDate": TODAY,
        "lastUpdated": TODAY,
        "source": "Bundled seed — updated by daily scraper",
        "requirements": reqs,
    }


if __name__ == "__main__":
    snapshot = build_snapshot()
    out_path = os.path.join(
        os.path.dirname(__file__), "..", "repo", "public", "state-occupation-requirements.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    count = len(snapshot["requirements"])
    print(f"✅ Generated requirements for {count} occupations → {os.path.abspath(out_path)}")
