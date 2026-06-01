#!/usr/bin/env python3
"""
Fetch all ANZSCO occupations from Jobs and Skills Australia with full details
"""

import json
import re
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

SITEMAP_URL = "https://www.jobsandskills.gov.au/sitemap-default.xml"
BASE_URL = "https://www.jobsandskills.gov.au"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
}

def extract_occupation_info(url: str) -> dict | None:
    """Fetch occupation name from JSA page"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        
        # Extract ANZSCO code
        code_match = re.search(r'/occupations/(\d+)-', url)
        if not code_match:
            return None
        
        anzsco = code_match.group(1)
        
        # Extract occupation name from title or h1
        title_match = re.search(r'<title[^>]*>([^<]+)</title>', resp.text)
        h1_match = re.search(r'<h1[^>]*>([^<]+)</h1>', resp.text)
        
        name = None
        if h1_match:
            name = h1_match.group(1).strip()
        elif title_match:
            name = title_match.group(1).split('|')[0].strip()
        
        if name:
            return {
                "anzsco": anzsco,
                "name": name,
                "url": url,
            }
    except Exception as e:
        print(f"  ⚠️  Error fetching {url}: {e}")
    
    return None

def main():
    print("=== Full ANZSCO Scraper (with occupations names) ===\n")
    
    # Fetch sitemap
    try:
        resp = requests.get(SITEMAP_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ Error fetching sitemap: {e}")
        return
    
    # Parse XML
    try:
        root = ET.fromstring(resp.content)
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        urls = [elem.text for elem in root.findall('.//ns:loc', namespace)]
        print(f"📍 Found {len(urls)} URLs in sitemap")
    except Exception as e:
        print(f"❌ Error parsing sitemap: {e}")
        return
    
    # Filter occupation URLs (only 6-digit codes for specific occupations)
    occupation_urls = [u for u in urls if re.search(r'/occupations/\d{6}-', u)]
    print(f"🎯 Found {len(occupation_urls)} 6-digit occupation URLs\n")
    
    # Fetch occupation details in parallel
    occupations_dict = {}
    print("⏳ Fetching occupation names (this may take a few minutes)...\n")
    
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(extract_occupation_info, url): url for url in occupation_urls}
        completed = 0
        
        for future in as_completed(futures):
            completed += 1
            if completed % 50 == 0:
                print(f"  Progress: {completed}/{len(occupation_urls)}")
            
            result = future.result()
            if result:
                code = result['anzsco']
                if code not in occupations_dict or len(result['name']) > len(occupations_dict[code]['name']):
                    occupations_dict[code] = result
    
    # Convert to sorted list
    occupations = [
        {
            "anzsco": code,
            "name": occupations_dict[code].get('name', f'Occupation {code}'),
            "lists": [],
            "visas": [],
            "assessingAuthority": None,
            "group": "Various",
        }
        for code in sorted(occupations_dict.keys())
    ]
    
    # Export
    output = {
        "snapshotDate": datetime.now().isoformat().split('T')[0],
        "lastUpdated": datetime.now().isoformat(),
        "items": occupations,
    }
    
    output_file = Path(__file__).parent.parent / "public" / "all-anzsco-occupations.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✅ Done!")
    print(f"   Total occupations: {len(occupations)}")
    print(f"   File size: {output_file.stat().st_size / 1024:.1f} KB")
    print(f"   Saved to: {output_file}")


if __name__ == "__main__":
    main()
