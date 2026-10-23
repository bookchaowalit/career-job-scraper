"""The flights data product was retired on 2026-10-23.

data-product-contracts-v4 (architecture-docs e11e074, owner approved) retired
flight.v1 / :8105 and bookchaowalit/travel-flight-price-data is to be archived.
Nothing in this repository may schedule, scrape, read, summarise or publish
flight prices any more.
"""

import re
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
FLIGHT_RE = re.compile(
    r"\bflights?\b|flight_prices|book-travel|book-flight-data|tequila", re.IGNORECASE
)
RUNTIME_SCRIPTS = (
    "scripts/generate_insights.py",
    "scripts/generate_pages.py",
    "scripts/publish_pages.py",
    "scripts/scraper_dashboard.py",
)


def _yaml(rel: str) -> dict:
    return yaml.safe_load((REPO_ROOT / rel).read_text(encoding="utf-8"))


class FlightsRetiredTests(unittest.TestCase):
    def test_scheduler_has_no_flight_job(self):
        names = [job["name"] for job in _yaml("config/jobs.yaml")["jobs"]]
        self.assertNotIn("flight_prices", names)

    def test_coverage_registry_has_no_flight_source_or_travel_lane(self):
        coverage = _yaml("config/source_coverage.yaml")
        self.assertNotIn("flight_prices", [s["job"] for s in coverage["sources"]])
        self.assertNotIn("travel", coverage["business_lanes"])

    def test_generators_and_dashboard_do_not_read_or_show_flights(self):
        for rel in RUNTIME_SCRIPTS:
            with self.subTest(script=rel):
                text = (REPO_ROOT / rel).read_text(encoding="utf-8")
                self.assertIsNone(
                    FLIGHT_RE.search(text), f"{rel} still mentions flights"
                )


if __name__ == "__main__":
    unittest.main()
