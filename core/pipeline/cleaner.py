"""
DataCleaner — normalize, validate, and enrich scraped data
Standardizes fields across different scraper outputs
"""
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
EXPORTED_DIR = DATA_DIR / "exported"

# Invisible format characters that ``str.strip()`` / ``\s`` do not remove:
# zero-width space (common as a Thai word-break hint in scraped HTML), word
# joiner, BOM / zero-width no-break space and soft hyphen. ZWJ/ZWNJ are kept
# because they change how emoji and some scripts render.
_INVISIBLE_RE = re.compile("[\u200b\u2060\ufeff\u00ad]")
_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def strip_invisible(text: str) -> str:
    """Remove zero-width/BOM characters that survive ``strip()``."""
    return _INVISIBLE_RE.sub("", text)


class DataCleaner:
    """
    Clean, normalize, and validate scraped data before export.
    
    Usage:
        cleaner = DataCleaner()
        clean_data = cleaner.clean(raw_items, schema="job")
        cleaner.export(clean_data, "jobs_cleaned.json")
    """

    # Common noise patterns to remove
    NOISE_PATTERNS = [
        r"\s+",                    # multiple spaces
        r"[\x00-\x08\x0b\x0c]",  # control characters
        r"\.{3,}",                # 3+ dots
    ]

    # Thai text patterns
    # 9-digit landlines (02-123-4567) and 10-digit mobiles (081-234-5678),
    # with optional single space/hyphen separators; never ends on a separator.
    THAI_PHONE_RE = re.compile(r"(?:\+66[\s-]?|0)\d(?:[\s-]?\d){7,8}")
    THAI_POSTAL_RE = re.compile(r"\b\d{5}\b")
    EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    URL_RE = re.compile(r"https?://[^\s<>\"']+")
    # Must start with a digit so a bare comma ("Negotiable, DOE") never matches.
    PRICE_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
    SALARY_NUMBER_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*([kK](?![a-zA-Z]))?")
    # A title suffix separator needs whitespace on both sides so hyphenated
    # words ("Front-End Developer") are not truncated.
    TITLE_SUFFIX_RE = re.compile(r"\s+[-–|]\s+.*$")
    THAI_TEXT_RE = re.compile(r"[\u0E00-\u0E7F]")

    def __init__(self):
        self.stats = {
            "input": 0,
            "output": 0,
            "removed_empty": 0,
            "removed_invalid": 0,
            "normalized": 0,
        }

    def clean(
        self,
        items: List[dict],
        schema: Optional[str] = None,
        remove_empty: bool = True,
        normalize_text: bool = True,
    ) -> List[dict]:
        """
        Clean a list of scraped items.
        
        Args:
            items: Raw scraped data
            schema: Optional schema hint ("job", "product", "business", "news")
            remove_empty: Remove items with no useful data
            normalize_text: Normalize whitespace, case, etc.
        
        Returns:
            Cleaned list of items
        """
        self.stats["input"] = len(items)
        cleaned = []

        for item in items:
            # Work on a copy: callers' dicts must not gain _cleaned_at/_schema
            # or schema edits (normalize_text=False used to mutate them).
            item = dict(item)
            # Skip empty items
            if remove_empty and self._is_empty(item):
                self.stats["removed_empty"] += 1
                continue

            # Normalize text fields
            if normalize_text:
                item = self._normalize_item(item)

            # Schema-specific cleaning
            if schema:
                item = self._apply_schema(item, schema)

            # Add metadata
            item["_cleaned_at"] = datetime.now().isoformat()
            item["_schema"] = schema or "generic"

            cleaned.append(item)

        self.stats["output"] = len(cleaned)
        print(f"[Cleaner] {self.stats['input']} items → {len(cleaned)} cleaned")
        return cleaned

    def _is_empty(self, item: dict) -> bool:
        """Check if item has no meaningful data."""
        if not item:
            return True
        # Check if all values are empty/None
        meaningful = [
            v for v in item.values()
            if v is not None and strip_invisible(str(v)).strip() != ""
        ]
        return len(meaningful) == 0

    def _normalize_item(self, item: dict) -> dict:
        """Normalize all string fields in an item."""
        normalized: dict[str, Any] = {}
        for key, value in item.items():
            if isinstance(value, str):
                normalized[key] = self._normalize_string(value)
                if normalized[key] != value:
                    self.stats["normalized"] += 1
            elif isinstance(value, list):
                normalized[key] = [
                    self._normalize_string(v) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                normalized[key] = value
        return normalized

    def _normalize_string(self, text: str) -> str:
        """Normalize a single string value."""
        # Remove control characters
        text = re.sub(r"[\x00-\x08\x0b\x0c]", "", text)
        text = strip_invisible(text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        # Strip leading/trailing whitespace
        text = text.strip()
        # Remove trailing dots/ellipses
        text = re.sub(r"\.{3,}$", "", text)
        return text

    def _apply_schema(self, item: dict, schema: str) -> dict:
        """Apply schema-specific cleaning rules."""
        cleaners = {
            "job": self._clean_job,
            "product": self._clean_product,
            "business": self._clean_business,
            "news": self._clean_news,
            "property": self._clean_property,
        }
        cleaner_fn = cleaners.get(schema)
        if cleaner_fn:
            return cleaner_fn(item)
        return item

    def _clean_job(self, item: dict) -> dict:
        """Clean job listing data."""
        # Normalize salary
        salary = item.get("salary", "")
        if salary:
            item["salary"] = self._normalize_salary(salary)

        # Normalize location
        location = item.get("location", "")
        if location:
            item["location"] = self._normalize_thai_address(location)

        # Clean title
        title = item.get("title", "")
        if title:
            item["title"] = self.TITLE_SUFFIX_RE.sub("", title).strip()

        return item

    def _clean_product(self, item: dict) -> dict:
        """Clean product data."""
        # Normalize price
        price = item.get("price", "")
        if price:
            item["price"] = self._normalize_price(price)

        # Clean product name
        name = item.get("name", "")
        if name:
            item["name"] = re.sub(r"\s*[|/]\s*(free shipping|ส่งฟรี).*", "", name, flags=re.I).strip()

        return item

    def _clean_business(self, item: dict) -> dict:
        """Clean business listing data."""
        # Extract phone if not present
        if not item.get("phone"):
            desc = item.get("description", "")
            phones = self.THAI_PHONE_RE.findall(desc)
            if phones:
                item["phone"] = phones[0].strip()

        # Normalize address
        address = item.get("address", "")
        if address:
            item["address"] = self._normalize_thai_address(address)

        return item

    def _clean_news(self, item: dict) -> dict:
        """Clean news article data."""
        # Clean title
        title = item.get("title", "")
        if title:
            item["title"] = self.TITLE_SUFFIX_RE.sub("", title).strip()

        # Normalize published date
        pub = item.get("published", "")
        if pub:
            item["published"] = self._normalize_date(pub)

        return item

    def _clean_property(self, item: dict) -> dict:
        """Clean property listing data."""
        price = item.get("price", "")
        if price:
            item["price"] = self._normalize_price(price)
        return item

    def _normalize_salary(self, salary: str) -> str:
        """Normalize salary to standard format."""
        salary = salary.strip()
        # Remove "บาท", "THB", "฿"
        salary = re.sub(r"(บาท|THB|฿)", "", salary, flags=re.I).strip()
        salary = salary.translate(_THAI_DIGITS)
        # Extract numbers; a "k"/"K" suffix ("30K - 50K") means thousands.
        numbers = self.SALARY_NUMBER_RE.findall(salary)
        if numbers:
            nums = [self._to_number(n, 1000 if k else 1) for n, k in numbers]
            if len(nums) == 2:
                return f"{nums[0]:,}-{nums[1]:,}"
            elif len(nums) == 1:
                return f"{nums[0]:,}"
        return salary.strip()

    @staticmethod
    def _to_number(text: str, scale: int = 1):
        """Parse "12,500" or "1.5" into int/float (int when it is whole)."""
        value = float(text.replace(",", "")) * scale
        return int(value) if value.is_integer() else value

    def _normalize_price(self, price: str) -> str:
        """Normalize price to number."""
        if not price:
            return ""
        # Remove currency symbols
        price = re.sub(r"[฿$€£,]", "", str(price).translate(_THAI_DIGITS))
        numbers = self.PRICE_RE.findall(price)
        if numbers:
            return numbers[0]
        return price.strip()

    def _normalize_thai_address(self, address: str) -> str:
        """Normalize Thai address format."""
        # Collapse whitespace
        address = re.sub(r"\s+", " ", address).strip()
        # Standardize district/province separators
        address = re.sub(r"\s+เขต\s+", " เขต", address)
        address = re.sub(r"\s+จังหวัด\s+", " จ.", address)
        return address

    _THAI_MONTHS = {
        "ม.ค.": 1, "มกราคม": 1, "ก.พ.": 2, "กุมภาพันธ์": 2, "มี.ค.": 3, "มีนาคม": 3,
        "เม.ย.": 4, "เมษายน": 4, "พ.ค.": 5, "พฤษภาคม": 5, "มิ.ย.": 6, "มิถุนายน": 6,
        "ก.ค.": 7, "กรกฎาคม": 7, "ส.ค.": 8, "สิงหาคม": 8, "ก.ย.": 9, "กันยายน": 9,
        "ต.ค.": 10, "ตุลาคม": 10, "พ.ย.": 11, "พฤศจิกายน": 11, "ธ.ค.": 12, "ธันวาคม": 12,
    }
    # "13 มิ.ย. 2569", optionally followed by a time "14:30", "14.30 น." or
    # "14:30:05".
    _THAI_DATE = re.compile(
        r"^(\d{1,2})\s*(\S+?)\s*(\d{4})"
        r"(?:\s+(?:เวลา\s*)?(\d{1,2})[:.](\d{2})(?:[:.](\d{2}))?\s*(?:น\.?)?)?$"
    )
    _BUDDHIST_ERA_OFFSET = 543

    def _normalize_date(self, date_str: str) -> str:
        """Normalize Thai / Buddhist-era dates to ISO 8601 without losing data.

        "13 มิ.ย. 2569" and "13 มิถุนายน 2569" (Buddhist era) become
        "2026-06-13"; a Gregorian year ("13 มิ.ย. 2026") is kept. A trailing
        time is preserved ("13 มิ.ย. 2569 14:30 น." -> "2026-06-13T14:30:00").
        Anything else -- including ISO dates/datetimes with their time and
        timezone, RFC 2822 feed dates and unparseable text -- is returned
        whitespace-collapsed but otherwise unchanged, so no information is lost.
        """
        text = re.sub(r"\s+", " ", str(date_str or "")).strip()
        if not text:
            return text
        match = self._THAI_DATE.match(text)
        if not match:
            return text
        day, month_name, year = int(match[1]), match[2], int(match[3])
        month = self._THAI_MONTHS.get(month_name) or self._THAI_MONTHS.get(month_name + ".")
        if month is None:
            return text
        if year > 2400:  # Buddhist era
            year -= self._BUDDHIST_ERA_OFFSET
        try:
            if match[4] is None:
                return datetime(year, month, day).date().isoformat()
            return datetime(
                year, month, day, int(match[4]), int(match[5]), int(match[6] or 0)
            ).isoformat()
        except ValueError:
            return text

    def extract_contacts(self, text: str) -> dict:
        """
        Extract contact info from text (phone, email, URL).
        
        Returns:
            Dict with phones, emails, urls lists
        """
        return {
            "phones": self.THAI_PHONE_RE.findall(text),
            "emails": self.EMAIL_RE.findall(text),
            "urls": self.URL_RE.findall(text),
        }

    def export(self, items: List[dict], filename: str, format: str = "json"):
        """Export cleaned data to file."""
        EXPORTED_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXPORTED_DIR / filename

        if format == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, ensure_ascii=False)
        elif format == "jsonl":
            with open(output_path, "w", encoding="utf-8") as f:
                for item in items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")

        print(f"[Cleaner] Exported {len(items)} items → {output_path}")
        return output_path

    def report(self) -> dict:
        """Get cleaning stats report."""
        return {
            **self.stats,
            "removal_rate": f"{self.stats['removed_empty'] / max(self.stats['input'], 1) * 100:.1f}%",
        }

    def __repr__(self):
        return f"DataCleaner(processed={self.stats['output']})"
