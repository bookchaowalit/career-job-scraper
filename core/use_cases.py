"""
Core use cases — business logic orchestration.
These coordinate the scraping pipeline: fetch → clean → dedup → export.
"""
import time
from typing import Any, Dict, List, Optional
from .models import ScrapedItem, ScrapeJob, ScrapeResult
from .ports import ScraperPort, ExporterPort, StoragePort


class ScrapeUseCase:
    """
    Main use case: Execute a scraping job end-to-end.
    
    Pipeline: scrape → clean → dedup → export → notify
    """

    def __init__(
        self,
        scraper: ScraperPort,
        exporter: ExporterPort,
        storage: StoragePort,
    ):
        self.scraper = scraper
        self.exporter = exporter
        self.storage = storage

    async def execute(self, job: ScrapeJob) -> ScrapeResult:
        """
        Execute a scrape job through the full pipeline.
        
        Args:
            job: The scrape job configuration
            
        Returns:
            ScrapeResult with stats and exported file paths
        """
        start_time = time.time()
        result = ScrapeResult(job_name=job.name, success=False)
        try:
            return await self._run(job, result)
        except Exception as e:
            result.success = False
            result.errors.append(f"Pipeline error: {str(e)}")
            return result
        finally:
            result.duration_seconds = time.time() - start_time

    async def _run(self, job: ScrapeJob, result: ScrapeResult) -> ScrapeResult:
        """Scrape -> clean -> dedup -> export -> save; errors propagate to execute()."""
        # Step 1: Scrape raw data
        items = await self.scraper.scrape(job)
        result.items_scraped = len(items)

        if not items:
            result.errors.append("No items scraped")
            return result

        # Step 2: Clean data
        cleaned_items = self._clean_items(items)
        result.items_cleaned = len(cleaned_items)

        # Step 3: Deduplicate
        new_items = self._deduplicate(cleaned_items)
        result.items_new = len(new_items)

        if not new_items:
            result.success = True
            result.errors.append("All items were duplicates")
            return result

        # Step 4: Export
        exported_paths = self._export(new_items, job.name)
        result.exported_to = exported_paths

        # Step 5: Save to storage
        self.storage.save(new_items, collection=job.category)

        result.success = True
        return result

    def _clean_items(self, items: List[ScrapedItem]) -> List[ScrapedItem]:
        """Clean and normalize scraped items."""
        cleaned = []
        for item in items:
            # Basic cleaning
            if hasattr(item, 'title'):
                item.title = item.title.strip()
            if hasattr(item, 'description'):
                item.description = item.description.strip()
            item.cleaned = True
            cleaned.append(item)
        return cleaned

    def _deduplicate(self, items: List[ScrapedItem]) -> List[ScrapedItem]:
        """Remove duplicates based on URL."""
        seen_urls = set()
        unique = []
        for item in items:
            if item.url and item.url not in seen_urls:
                seen_urls.add(item.url)
                unique.append(item)
            elif not item.url:
                # Items without URL are kept
                unique.append(item)
        return unique

    def _export(self, items: List[ScrapedItem], job_name: str) -> List[str]:
        """Export items to configured formats."""
        paths = []
        # Export to JSON (always)
        json_path = self.exporter.export(items, "json", f"{job_name}.json")
        if json_path:
            paths.append(json_path)
        # Export to CSV (always)
        csv_path = self.exporter.export(items, "csv", f"{job_name}.csv")
        if csv_path:
            paths.append(csv_path)
        return paths


class SearchUseCase:
    """
    Use case for searching scraped data (used by MCP server).
    """

    def __init__(self, storage: StoragePort):
        self.storage = storage

    def search_jobs(
        self,
        keyword: str = "",
        location: str = "",
        limit: int = 20,
    ) -> List[ScrapedItem]:
        """Search job listings."""
        limit = max(0, limit)
        filters = {}
        if keyword:
            filters["title_contains"] = keyword
        if location:
            filters["location_contains"] = location
        items = self.storage.load("jobs", filters)
        return items[:limit]

    def search_businesses(
        self,
        category: str = "",
        area: str = "",
        limit: int = 20,
    ) -> List[ScrapedItem]:
        """Search business listings."""
        limit = max(0, limit)
        filters = {}
        if category:
            filters["category"] = category
        if area:
            filters["area"] = area
        items = self.storage.load("businesses", filters)
        return items[:limit]

    def search_products(
        self,
        keyword: str = "",
        max_price: Optional[float] = None,
        limit: int = 20,
    ) -> List[ScrapedItem]:
        """Search product listings."""
        limit = max(0, limit)
        filters: Dict[str, Any] = {}
        if keyword:
            filters["name_contains"] = keyword
        if max_price is not None:  # 0 is a valid (if strict) ceiling
            filters["price_lte"] = max_price
        items = self.storage.load("products", filters)
        return items[:limit]
