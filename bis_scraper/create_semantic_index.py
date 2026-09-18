#!/usr/bin/env python3
"""
Create semantic indices and additional metadata for RAG systems.
Generates category mappings, domain hierarchies, and reference networks.
"""

import json
from pathlib import Path
from collections import defaultdict
import pandas as pd


class SemanticIndexGenerator:
    """Generate semantic indices for RAG systems"""
    
    def __init__(self, data_dir: str = "bis_data"):
        self.data_dir = Path(data_dir)
        self.merged_csv = self.data_dir / "merged" / "merged_standards.csv"
        self.output_dir = self.data_dir / "semantic"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def create_category_hierarchy(self) -> dict:
        """Create hierarchical category structure"""
        print("Creating category hierarchy...")
        
        df = pd.read_csv(self.merged_csv)
        
        hierarchy = {
            'divisions': {},
            'committees': {},
            'categories': defaultdict(list)
        }
        
        # Map divisions
        for div in df['division'].unique():
            if pd.notna(div):
                standards = df[df['division'] == div]['canonical'].tolist()
                hierarchy['divisions'][str(div)] = {
                    'count': len(standards),
                    'standards': standards
                }
        
        # Map committees
        for comm in df['committee'].unique():
            if pd.notna(comm):
                standards = df[df['committee'] == comm]['canonical'].tolist()
                hierarchy['committees'][str(comm)] = {
                    'count': len(standards),
                    'standards': standards
                }
        
        # Categorize by number ranges (IS numbering patterns)
        ranges = [
            ('Early Standards (1-100)', 1, 100),
            ('Textiles (100-500)', 100, 500),
            ('Chemical (500-1000)', 500, 1000),
            ('Electrical (1000-2000)', 1000, 2000),
            ('Civil Engineering (2000-5000)', 2000, 5000),
            ('Testing & Methods (5000-10000)', 5000, 10000),
            ('Modern Standards (10000+)', 10000, 99999),
        ]
        
        for range_name, start, end in ranges:
            # Extract number from canonical
            standards_in_range = []
            for canonical in df['canonical']:
                try:
                    parts = canonical.split('|')
                    if len(parts) > 2:
                        num = int(parts[2])
                        if start <= num <= end:
                            standards_in_range.append(canonical)
                except:
                    pass
            
            if standards_in_range:
                hierarchy['categories'][range_name] = {
                    'count': len(standards_in_range),
                    'standards': standards_in_range
                }
        
        # Save hierarchy
        output_file = self.output_dir / "category_hierarchy.json"
        with open(output_file, 'w') as f:
            # Convert defaultdict to regular dict
            hierarchy['categories'] = dict(hierarchy['categories'])
            json.dump(hierarchy, f, indent=2)
        
        print(f"✓ Created category hierarchy with {len(hierarchy['divisions'])} divisions")
        return hierarchy
    
    def create_cross_references(self) -> dict:
        """Create cross-reference network"""
        print("Creating cross-reference network...")
        
        df = pd.read_csv(self.merged_csv)
        cross_refs = {
            'supersession_chains': {},
            'related_by_division': {},
            'related_by_committee': {},
            'latest_editions': []
        }
        
        # Track supersession chains
        for idx, row in df.iterrows():
            if pd.notna(row['superseded_by']) and row['superseded_by'] != '':
                old_id = row['canonical']
                new_id = row['superseded_by']
                cross_refs['supersession_chains'][old_id] = new_id
        
        # Group by division
        for div in df['division'].unique():
            if pd.notna(div):
                standards = df[df['division'] == div]['canonical'].tolist()
                if standards:
                    cross_refs['related_by_division'][str(div)] = standards
        
        # Group by committee
        for comm in df['committee'].unique():
            if pd.notna(comm):
                standards = df[df['committee'] == comm]['canonical'].tolist()
                if standards:
                    cross_refs['related_by_committee'][str(comm)] = standards
        
        # Latest editions
        latest = df[df['is_current'] == True]['canonical'].tolist()
        cross_refs['latest_editions'] = latest
        
        output_file = self.output_dir / "cross_references.json"
        with open(output_file, 'w') as f:
            json.dump(cross_refs, f, indent=2)
        
        print(f"✓ Created cross-references with {len(cross_refs['supersession_chains'])} supersession chains")
        return cross_refs
    
    def create_domain_ontology(self) -> dict:
        """Create domain-specific ontology"""
        print("Creating domain ontology...")
        
        df = pd.read_csv(self.merged_csv)
        
        ontology = {
            'domains': {},
            'relationships': [],
            'concepts': {}
        }
        
        # Build domain structure
        domains = {}
        for idx, row in df.iterrows():
            div = row['division']
            if pd.notna(div):
                if div not in domains:
                    domains[div] = {
                        'standards': [],
                        'committees': set(),
                        'year_range': [row['year'], row['year']]
                    }
                
                domains[div]['standards'].append({
                    'id': row['canonical'],
                    'title': row['title'],
                    'year': row['year']
                })
                domains[div]['committees'].add(str(row['committee']))
                
                # Update year range
                domains[div]['year_range'][0] = min(domains[div]['year_range'][0], row['year'])
                domains[div]['year_range'][1] = max(domains[div]['year_range'][1], row['year'])
        
        # Convert to serializable format
        for domain, data in domains.items():
            ontology['domains'][domain] = {
                'count': len(data['standards']),
                'standards': data['standards'],
                'committees': list(data['committees']),
                'year_range': data['year_range']
            }
        
        # Extract concepts (keywords from titles)
        concepts = defaultdict(set)
        for idx, row in df.iterrows():
            title = str(row['title']).lower()
            # Simple keyword extraction
            keywords = [w for w in title.split() if len(w) > 4]
            for keyword in keywords:
                concepts[keyword].add(row['canonical'])
        
        ontology['concepts'] = {k: list(v) for k, v in sorted(concepts.items()) if len(v) > 1}
        
        output_file = self.output_dir / "domain_ontology.json"
        with open(output_file, 'w') as f:
            json.dump(ontology, f, indent=2)
        
        print(f"✓ Created domain ontology with {len(ontology['domains'])} domains")
        return ontology
    
    def create_temporal_index(self) -> dict:
        """Create temporal/chronological index"""
        print("Creating temporal index...")
        
        df = pd.read_csv(self.merged_csv)
        
        temporal = {
            'by_year': {},
            'by_decade': {},
            'evolution': {},
            'statistics': {}
        }
        
        # By year
        for year in sorted(df['year'].unique()):
            standards = df[df['year'] == year]['canonical'].tolist()
            temporal['by_year'][int(year)] = {
                'count': len(standards),
                'standards': standards
            }
        
        # By decade
        for decade in sorted(set(int(y // 10) * 10 for y in df['year'].unique())):
            decade_standards = df[(df['year'] >= decade) & (df['year'] < decade + 10)]['canonical'].tolist()
            temporal['by_decade'][decade] = {
                'count': len(decade_standards),
                'standards': decade_standards
            }
        
        # Evolution (supersession over time)
        for idx, row in df.iterrows():
            if pd.notna(row['superseded_by']) and row['superseded_by'] != '':
                base_num = row['designation'].split(':')[0]
                if base_num not in temporal['evolution']:
                    temporal['evolution'][base_num] = []
                temporal['evolution'][base_num].append({
                    'old_year': row['year'],
                    'designation': row['designation'],
                    'superseded_by': row['superseded_by']
                })
        
        # Statistics
        temporal['statistics'] = {
            'earliest_year': int(df['year'].min()),
            'latest_year': int(df['year'].max()),
            'total_standards': len(df),
            'current_standards': int(df['is_current'].sum()),
            'superseded_standards': int((~df['is_current']).sum()),
            'average_year': int(df['year'].mean())
        }
        
        output_file = self.output_dir / "temporal_index.json"
        with open(output_file, 'w') as f:
            json.dump(temporal, f, indent=2)
        
        print(f"✓ Created temporal index with evolution tracking")
        return temporal
    
    def create_search_facets(self) -> dict:
        """Create faceted search structure"""
        print("Creating search facets...")
        
        df = pd.read_csv(self.merged_csv)
        
        facets = {
            'facets': {}
        }
        
        # Division facet
        divisions = df['division'].dropna().unique()
        facets['facets']['division'] = {
            'type': 'categorical',
            'values': [{'name': str(d), 'count': len(df[df['division'] == d])} for d in sorted(divisions)]
        }
        
        # Year facet
        years = sorted(df['year'].unique())
        facets['facets']['year'] = {
            'type': 'range',
            'min': int(df['year'].min()),
            'max': int(df['year'].max()),
            'values': [{'year': int(y), 'count': len(df[df['year'] == y])} for y in years]
        }
        
        # Current/Superseded facet
        facets['facets']['status'] = {
            'type': 'categorical',
            'values': [
                {'name': 'current', 'count': int(df['is_current'].sum())},
                {'name': 'superseded', 'count': int((~df['is_current']).sum())}
            ]
        }
        
        # Committee facet
        committees = df['committee'].dropna().unique()
        facets['facets']['committee'] = {
            'type': 'categorical',
            'values': [{'name': str(c), 'count': len(df[df['committee'] == c])} for c in sorted(committees)]
        }
        
        output_file = self.output_dir / "search_facets.json"
        with open(output_file, 'w') as f:
            json.dump(facets, f, indent=2)
        
        print(f"✓ Created search facets with multiple dimensions")
        return facets
    
    def generate_all(self) -> dict:
        """Generate all semantic indices"""
        print("\n" + "="*60)
        print("GENERATING SEMANTIC INDICES FOR RAG")
        print("="*60 + "\n")
        
        results = {
            'category_hierarchy': self.create_category_hierarchy(),
            'cross_references': self.create_cross_references(),
            'domain_ontology': self.create_domain_ontology(),
            'temporal_index': self.create_temporal_index(),
            'search_facets': self.create_search_facets(),
        }
        
        print("\n" + "="*60)
        print("SEMANTIC INDEXING COMPLETE!")
        print("="*60)
        print("\nGenerated files in bis_data/semantic/:")
        print("  ✓ category_hierarchy.json")
        print("  ✓ cross_references.json")
        print("  ✓ domain_ontology.json")
        print("  ✓ temporal_index.json")
        print("  ✓ search_facets.json")
        
        return results


if __name__ == "__main__":
    generator = SemanticIndexGenerator()
    generator.generate_all()
