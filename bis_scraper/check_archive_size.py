#!/usr/bin/env python3
"""Check how many standards are available in archive.org"""

import requests
import json
from pathlib import Path

def check_archive_stats():
    """Get statistics on archive.org gov.in.is collection"""
    
    # Query archive.org for all gov.in.is items
    url = 'https://archive.org/advancedsearch.php'
    params = {
        'q': 'collection:(gov.in.is)',
        'fl': 'identifier,title',
        'output': 'json',
        'rows': 50000
    }
    
    print('Querying archive.org for all standards...')
    try:
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        
        docs = data.get('response', {}).get('docs', [])
        print(f'\nFound: {len(docs)} standards in archive.org collection')
        
        # Count current extraction
        items_file = Path('bis_data/archive/items.jsonl')
        extracted = 0
        if items_file.exists():
            with open(items_file) as f:
                extracted = len(f.readlines())
        
        print(f'Currently extracted: {extracted} standards')
        print(f'Remaining to extract: {len(docs) - extracted} standards')
        print(f'\nCollection size: ~{len(docs)} standards available')
        
        # Show samples
        if docs:
            print(f'\nFirst 5 standards:')
            for doc in docs[:5]:
                print(f'  • {doc.get("identifier")}')
            
            print(f'\nLast 5 standards:')
            for doc in docs[-5:]:
                print(f'  • {doc.get("identifier")}')
        
        return len(docs)
        
    except Exception as e:
        print(f'Error: {e}')
        return 0

if __name__ == '__main__':
    check_archive_stats()
