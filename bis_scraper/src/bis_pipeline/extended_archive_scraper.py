"""
Extended archive scraper to maximize data extraction for RAG.
Uses multiple strategies to maximize dataset size from archive.org
"""

import json
import logging
from pathlib import Path
from typing import Generator, Optional
from .http import Client
from .iscode import IsCode

logger = logging.getLogger(__name__)


class ExtendedArchiveScraper:
    """Enhanced scraper to get maximum data from archive.org"""

    def __init__(self, http_client: Optional[Client] = None, cache_dir: Path = None):
        self.http_client = http_client or Client()
        self.cache_dir = cache_dir or Path("bis_data/archive")
        self.items_file = self.cache_dir / "items.jsonl"

    def scrape_by_range(self, start: int = 1, end: int = 20000) -> Generator:
        """Scrape by IS number ranges to maximize coverage"""
        logger.info(f"Scraping IS numbers {start}-{end}")
        
        # Direct IS number ranges based on historical patterns
        ranges = [
            (1, 100),           # Early standards
            (100, 500),         # Textiles & early engineering
            (500, 1000),        # Chemical & materials
            (1000, 2000),       # Electrical & engineering
            (2000, 5000),       # Civil engineering
            (5000, 10000),      # Testing & methods
            (10000, 12000),     # Modern standards
            (12000, 20000),     # Latest standards
        ]
        
        for start_num, end_num in ranges:
            for num in range(start_num, end_num + 1, 1):
                # Try different part/section combinations
                variants = [
                    f"gov.in.is.{num}",
                    f"gov.in.is.{num}.1",
                    f"gov.in.is.{num}.2",
                ]
                
                for identifier in variants:
                    try:
                        # Check if item exists
                        metadata_url = f"https://archive.org/metadata/{identifier}"
                        resp = self.http_client.get(metadata_url, timeout=5)
                        
                        if resp.status_code == 200:
                            item_data = resp.json()
                            if item_data.get("files"):
                                logger.info(f"Found: {identifier}")
                                yield item_data
                    except Exception as e:
                        logger.debug(f"Skipped {identifier}: {e}")
                        continue

    def scrape_by_collection_search(self, query: str = "indian standards") -> Generator:
        """Use archive.org search API to find standards"""
        logger.info(f"Searching archive.org for: {query}")
        
        rows = 200
        for start in range(0, 50000, rows):  # Up to 50k results
            try:
                search_url = (
                    f"https://archive.org/advancedsearch.php?"
                    f"q=collection%3A%28gov.in.is%29&fl=identifier&sort=identifier&rows={rows}"
                    f"&output=json&start={start}"
                )
                
                resp = self.http_client.get(search_url, timeout=10)
                data = resp.json()
                
                for doc in data.get("response", {}).get("docs", []):
                    identifier = doc.get("identifier")
                    if identifier:
                        try:
                            metadata_url = f"https://archive.org/metadata/{identifier}"
                            meta_resp = self.http_client.get(metadata_url, timeout=5)
                            if meta_resp.status_code == 200:
                                logger.info(f"Found: {identifier}")
                                yield meta_resp.json()
                        except Exception as e:
                            logger.debug(f"Failed to get metadata: {e}")
                            continue
                
                if not data.get("response", {}).get("docs"):
                    break
                    
            except Exception as e:
                logger.warning(f"Search error at start={start}: {e}")
                break

    def scrape_all_available(self, max_items: Optional[int] = None) -> int:
        """Scrape all available standards using multiple strategies"""
        
        # Load existing items
        existing = set()
        if self.items_file.exists():
            with open(self.items_file) as f:
                for line in f:
                    item = json.loads(line)
                    existing.add(item.get("identifier"))
        
        logger.info(f"Starting with {len(existing)} existing items")
        
        count = len(existing)
        
        # Strategy 1: Collection search
        logger.info("=== Strategy 1: Collection Search ===")
        for item_data in self.scrape_by_collection_search():
            identifier = item_data.get("metadata", {}).get("identifier")
            if identifier and identifier not in existing:
                self._write_item(item_data)
                existing.add(identifier)
                count += 1
                
                if max_items and count >= max_items:
                    logger.info(f"Reached max items: {count}")
                    return count
        
        # Strategy 2: Range-based scraping
        logger.info("=== Strategy 2: Range-based Scraping ===")
        for item_data in self.scrape_by_range():
            identifier = item_data.get("metadata", {}).get("identifier")
            if identifier and identifier not in existing:
                self._write_item(item_data)
                existing.add(identifier)
                count += 1
                
                if count % 100 == 0:
                    logger.info(f"Progress: {count} items")
                
                if max_items and count >= max_items:
                    logger.info(f"Reached max items: {count}")
                    return count
        
        logger.info(f"Extraction complete: {count} total items")
        return count

    def _write_item(self, item_data: dict):
        """Write item to JSONL file"""
        self.items_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.items_file, "a") as f:
            json.dump(item_data, f)
            f.write("\n")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = ExtendedArchiveScraper()
    scraper.scrape_all_available(max_items=10000)
