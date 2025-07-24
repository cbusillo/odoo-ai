#!/usr/bin/env python3
"""
Crowley Marine Parts Catalog Import Script

This standalone script imports marine parts data from crowleymarine.com into Odoo
using the XML-RPC API. It runs outside of the Odoo environment to avoid conflicts.

Usage:
    python tools/crowley_marine_import.py [--manufacturers mercury,yamaha] [--test]
"""

import asyncio
import argparse
import json
import logging
import os
import re
import sys
import xmlrpc.client
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs

# Playwright imports
try:
    from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout
except ImportError:
    print("ERROR: Playwright not installed. Please run: pip install playwright")
    print("Then run: playwright install chromium")
    sys.exit(1)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class OdooConnector:
    """Handles connection to Odoo via XML-RPC API"""

    def __init__(self, url: str, db: str, api_key: str):
        self.url = url
        self.db = db
        self.api_key = api_key
        self.uid = 2  # UID 2 is used for API key authentication
        self.models = None

    def connect(self):
        """Establish connection to Odoo"""
        try:
            # Models endpoint for data operations
            self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

            # Test connection by checking access
            self.models.execute_kw(
                self.db, self.uid, self.api_key, "res.users", "check_access_rights", ["read"], {"raise_exception": False}
            )

            logger.info(f"Connected to Odoo at {self.url} using API key")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Odoo: {e}")
            return False

    def execute(self, model: str, method: str, *args, **kwargs):
        """Execute method on Odoo model"""
        return self.models.execute_kw(self.db, self.uid, self.api_key, model, method, list(args), kwargs)

    def create(self, model: str, vals: Dict):
        """Create a record"""
        result = self.execute(model, "create", [vals])
        # XML-RPC returns list with single ID
        return result[0] if isinstance(result, list) else result

    def search(self, model: str, domain: List, limit: int = None):
        """Search for records"""
        kwargs = {}
        if limit:
            kwargs["limit"] = limit
        return self.execute(model, "search", domain, **kwargs)

    def search_read(self, model: str, domain: List, fields: List = None, limit: int = None):
        """Search and read records"""
        kwargs = {}
        if fields:
            kwargs["fields"] = fields
        if limit:
            kwargs["limit"] = limit
        return self.execute(model, "search_read", domain, **kwargs)

    def write(self, model: str, ids: List[int], vals: Dict):
        """Update records"""
        return self.execute(model, "write", ids, vals)


class CrowleyMarineScraper:
    """Scraper for crowleymarine.com marine parts catalog"""

    BASE_URL = "https://www.crowleymarine.com"

    # Major marine manufacturers on Crowley
    MANUFACTURERS = {
        "mercury": {
            "name": "Mercury",
            "base_url": "https://www.crowleymarine.com/mercury/parts/",
            "outboard_path": "/mercury/oem-parts/outboard",
            "types": ["outboard", "sterndrive"],
        },
        "yamaha": {"name": "Yamaha", "outboard_path": "/yamaha/oem-parts/outboard", "types": ["outboard"]},
        "johnson": {"name": "Johnson", "outboard_path": "/johnson/oem-parts/outboard", "types": ["outboard"]},
        "evinrude": {"name": "Evinrude", "outboard_path": "/evinrude/oem-parts/outboard", "types": ["outboard"]},
        "honda": {"name": "Honda Marine", "outboard_path": "/honda-marine/oem-parts/outboard", "types": ["outboard"]},
        "suzuki": {"name": "Suzuki", "outboard_path": "/suzuki/oem-parts/outboard", "types": ["outboard"]},
        "tohatsu": {"name": "Tohatsu", "outboard_path": "/tohatsu/oem-parts/outboard", "types": ["outboard"]},
        "mariner": {"name": "Mariner", "outboard_path": "/mariner/oem-parts/outboard", "types": ["outboard"]},
    }

    def __init__(self, odoo: OdooConnector):
        self.odoo = odoo
        self.manufacturers_cache = {}
        self.categories_cache = {}
        self.model_variants_cache = {}
        self.processed_parts = 0
        self.processed_variants = 0
        self.errors = []

    def get_or_create_manufacturer(self, name: str) -> int:
        """Get or create manufacturer in Odoo"""
        if name in self.manufacturers_cache:
            return self.manufacturers_cache[name]

        # Search for existing
        mfr_ids = self.odoo.search("product.manufacturer", [("name", "=", name)], limit=1)

        if mfr_ids:
            mfr_id = mfr_ids[0]
        else:
            # Create new
            mfr_id = self.odoo.create(
                "product.manufacturer",
                {
                    "name": name,
                },
            )
            logger.info(f"Created manufacturer: {name}")

        self.manufacturers_cache[name] = mfr_id
        return mfr_id

    def get_or_create_category(self, name: str, parent_id: int = None) -> int:
        """Get or create category in Odoo"""
        cache_key = f"{name}:{parent_id}"
        if cache_key in self.categories_cache:
            return self.categories_cache[cache_key]

        # Search for existing
        domain = [("name", "=", name)]
        if parent_id:
            domain.append(("parent_id", "=", parent_id))
        else:
            domain.append(("parent_id", "=", False))

        cat_ids = self.odoo.search("catalog.category", domain, limit=1)

        if cat_ids:
            cat_id = cat_ids[0]
        else:
            # Create new
            vals = {"name": name}
            if parent_id:
                vals["parent_id"] = parent_id
            cat_id = self.odoo.create("catalog.category", vals)
            logger.info(f"Created category: {name}")

        self.categories_cache[cache_key] = cat_id
        return cat_id

    def create_or_update_model_variant(self, variant_data: Dict) -> Optional[int]:
        """Create or update model variant in Odoo"""
        try:
            model_code = variant_data.get("model_code")
            if not model_code:
                logger.warning("Variant data missing model_code, skipping")
                return None

            # Search for existing variant
            variant_ids = self.odoo.search("catalog.model.variant", [("model_code", "=", model_code)], limit=1)

            # Prepare values - filter out None values
            vals = {
                "model_code": model_code,
                "manufacturer_id": variant_data.get("manufacturer_id"),
                "year": variant_data.get("year"),
                "horsepower": variant_data.get("horsepower", 0.0),
                "model_name": variant_data.get("model_name", ""),
                "shaft_length_code": variant_data.get("shaft_length_code", ""),
            }

            # Only add optional fields if they have values
            if variant_data.get("cylinders"):
                vals["cylinders"] = variant_data["cylinders"]
            if variant_data.get("displacement"):
                vals["displacement"] = variant_data["displacement"]
            if variant_data.get("serial_range_start"):
                vals["serial_range_start"] = variant_data["serial_range_start"]
            if variant_data.get("serial_range_end"):
                vals["serial_range_end"] = variant_data["serial_range_end"]

            if variant_ids:
                # Update existing
                self.odoo.write("catalog.model.variant", variant_ids, vals)
                logger.info(f"Updated model variant: {model_code}")
                variant_id = variant_ids[0]
            else:
                # Create new
                variant_id = self.odoo.create("catalog.model.variant", vals)
                logger.info(f"Created model variant: {model_code}")
                self.processed_variants += 1

            self.model_variants_cache[model_code] = variant_id
            return variant_id

        except Exception as e:
            logger.error(f"Error creating/updating variant {variant_data.get('model_code')}: {e}")
            self.errors.append(f"Variant {variant_data.get('model_code')}: {str(e)}")
            return None

    def create_or_update_part(self, part_data: Dict) -> Optional[int]:
        """Create or update part in Odoo"""
        try:
            mpn = part_data.get("mpn")
            if not mpn:
                logger.warning("Part data missing MPN, skipping")
                return None

            # Search for existing part (with uppercase MPN)
            part_ids = self.odoo.search("catalog.part", [("mpn", "=", mpn.upper().strip())], limit=1)

            # Prepare values
            vals = {
                "mpn": mpn.upper().strip(),  # Uppercase MPN to match constraint
                "name": part_data.get("name", mpn),
                "manufacturer_id": part_data.get("manufacturer_id"),
                "retail_price": part_data.get("retail_price", 0.0),
                "oem_numbers": part_data.get("oem_numbers", ""),
                "component_category": part_data.get("component_category", ""),
                "diagram_reference": part_data.get("diagram_reference", ""),
                "availability_status": part_data.get("availability_status", "in_stock"),
                "active": True,
            }

            # Only add category_id if provided
            if part_data.get("category_id"):
                vals["category_id"] = part_data["category_id"]

            # Handle model variant relationships
            if part_data.get("model_variant_ids"):
                vals["model_variant_ids"] = [(6, 0, part_data["model_variant_ids"])]

            if part_ids:
                # Update existing
                self.odoo.write("catalog.part", part_ids, vals)
                logger.info(f"Updated existing part: {mpn} (ID: {part_ids[0]})")
                self.processed_parts += 1
                return part_ids[0]
            else:
                # Create new
                part_id = self.odoo.create("catalog.part", vals)
                logger.info(f"Created new part: {mpn} (ID: {part_id})")
                self.processed_parts += 1
                return part_id

        except Exception as e:
            logger.error(f"Error creating/updating part {part_data.get('mpn')}: {e}")
            self.errors.append(f"Part {part_data.get('mpn')}: {str(e)}")
            return None

    async def scrape_manufacturer(self, page: Page, manufacturer_key: str):
        """Scrape all parts for a manufacturer"""
        mfr_info = self.MANUFACTURERS[manufacturer_key]
        manufacturer_id = self.get_or_create_manufacturer(mfr_info["name"])

        logger.info(f"Starting scrape for {mfr_info['name']}")

        try:
            # Navigate directly to outboard page
            outboard_url = f"{self.BASE_URL}{mfr_info.get('outboard_path', f'/{manufacturer_key}/oem-parts/outboard')}"
            logger.info(f"Navigating to: {outboard_url}")
            await page.goto(outboard_url, wait_until="networkidle")
            await page.wait_for_timeout(2000)

            # Check current URL
            current_url = page.url
            logger.info(f"Current URL: {current_url}")

            # Look for year links
            year_links = await page.locator("a").all()
            years_to_process = []
            logger.info(f"Checking {len(year_links)} links for years...")

            for link in year_links:
                href = await link.get_attribute("href")
                text = await link.text_content()
                if href and text and text.strip().isdigit():
                    year_int = int(text.strip())
                    # Check if it's a valid year (1950-2030)
                    if 1950 <= year_int <= 2030:
                        years_to_process.append((text.strip(), href))

            # Sort by year descending
            years_to_process.sort(key=lambda x: x[0], reverse=True)

            # Debug: Show available years
            if years_to_process:
                logger.info(f"Available years: {[y[0] for y in years_to_process[:10]]}")

            # Limit years in test mode
            if len(years_to_process) > 1:
                years_to_process = years_to_process[:1]
                logger.info(f"Test mode: Processing only {len(years_to_process)} recent years")

            # Create manufacturer category
            mfr_category_id = self.get_or_create_category(mfr_info["name"])

            # Process each year
            for year, year_url in years_to_process:
                await self.scrape_year_models(page, manufacturer_key, manufacturer_id, mfr_category_id, year, year_url)

        except Exception as e:
            logger.error(f"Error scraping {manufacturer_key}: {e}")
            self.errors.append(f"Manufacturer {manufacturer_key}: {str(e)}")

    async def scrape_year_models(
        self, page: Page, manufacturer_key: str, manufacturer_id: int, mfr_category_id: int, year: str, year_url: str
    ):
        """Scrape all models for a specific year"""
        try:
            logger.info(f"Processing {manufacturer_key} year {year}")

            # Navigate to year page
            full_url = urljoin(self.BASE_URL, year_url)
            logger.info(f"Navigating to: {full_url}")
            await page.goto(full_url, wait_until="networkidle")

            # Wait for content to load
            await page.wait_for_timeout(2000)

            # Debug: save page content
            content = await page.content()
            if "No results found" in content or "no models found" in content.lower():
                logger.warning(f"No models found for year {year}")
                return

            # Look for model links in the page
            # They typically have hrefs like: /mercury/oem-parts/outboard/2014/115ELPTO
            all_links = await page.locator("a").all()
            model_links = []

            for link in all_links:
                href = await link.get_attribute("href") or ""
                # Check if it's a model link (has year and model code in path)
                if f"/oem-parts/outboard/{year}/" in href:
                    model_links.append(link)

            logger.info(f"Found {len(model_links)} model links for year {year}")
            models_to_process = []

            for link in model_links:
                href = await link.get_attribute("href")
                text = await link.text_content()
                if href and text:
                    # Extract model info from text (e.g., "2.5 [M]" or "115 4-Stroke")
                    model_text = text.strip()
                    # Extract model code from URL (last part)
                    model_code = href.rstrip("/").split("/")[-1]
                    # Skip invalid model codes
                    if model_code and model_code != year and not model_code.startswith("oem-parts"):
                        models_to_process.append((model_text, model_code, href))
                        if len(models_to_process) <= 5:  # Log first few
                            logger.info(f"Found model: {model_text} - {model_code} - {href}")

            # Limit models in test mode
            if len(models_to_process) > 1:
                models_to_process = models_to_process[:1]
                logger.info(f"Test mode: Processing only {len(models_to_process)} models for year {year}")
            else:
                logger.info(f"Processing all {len(models_to_process)} models for year {year}")

            # Process each model
            for model_text, model_code, model_url in models_to_process:
                # Parse model info - extract horsepower if in model text
                hp_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:HP|hp|[Hh]orsepower)", model_text)
                if not hp_match:
                    # Try just numbers less than 600
                    hp_match = re.search(r"\b(\d{1,3}(?:\.\d+)?)\b", model_text)
                    if hp_match and float(hp_match.group(1)) > 600:
                        hp_match = None

                horsepower = float(hp_match.group(1)) if hp_match else 0.0

                # Extract shaft code if present (e.g., [M], [ML], etc.)
                shaft_match = re.search(r"\[([A-Z]+)\]", model_text)
                shaft_code = shaft_match.group(1) if shaft_match else ""

                # Create model variant
                variant_data = {
                    "model_code": model_code.upper(),
                    "manufacturer_id": manufacturer_id,
                    "year": year,
                    "horsepower": horsepower,
                    "model_name": model_text.split("[")[0].strip(),
                    "shaft_length_code": shaft_code,
                }

                variant_id = self.create_or_update_model_variant(variant_data)

                if variant_id:
                    # Scrape parts for this model
                    logger.info(f"Scraping parts for model variant {model_code}")
                    await self.scrape_model_parts(page, manufacturer_id, mfr_category_id, variant_id, model_url)

        except Exception as e:
            logger.error(f"Error processing year {year}: {e}")
            self.errors.append(f"Year {year}: {str(e)}")

    async def scrape_model_parts(self, page: Page, manufacturer_id: int, mfr_category_id: int, variant_id: int, model_url: str):
        """Scrape parts for a specific model"""
        try:
            # Navigate to model page
            full_url = urljoin(self.BASE_URL, model_url)
            logger.info(f"Navigating to model page: {full_url}")
            await page.goto(full_url, wait_until="networkidle")
            await page.wait_for_timeout(2000)

            # Get component categories - they should have the same model code in URL
            current_model_code = model_url.rstrip("/").split("/")[-1]
            all_links = await page.locator("a").all()
            component_links = []

            for link in all_links:
                href = await link.get_attribute("href") or ""
                # Component links should contain the current model code
                if f"/{current_model_code}/" in href and href != model_url:
                    component_links.append(link)

            logger.info(f"Found {len(component_links)} component links for model {current_model_code}")

            # Limit components in test mode
            components_to_process = []
            for link in component_links[:1]:  # Process only first component in test mode
                href = await link.get_attribute("href")
                text = await link.text_content()
                if href and text and not any(skip in text.lower() for skip in ["catalog", "manual", "back to"]):
                    components_to_process.append((text.strip(), href))

            logger.info(f"Processing {len(components_to_process)} components for this model")

            # Process each component
            for component_name, component_url in components_to_process:
                logger.info(f"Processing component: {component_name}")
                # Create component category
                component_category_id = self.get_or_create_category(component_name, mfr_category_id)

                # Navigate to component page
                full_component_url = urljoin(self.BASE_URL, component_url)
                logger.info(f"Navigating to component: {full_component_url}")
                await page.goto(full_component_url, wait_until="networkidle")
                await page.wait_for_timeout(2000)

                # Scroll down to load parts list
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)

                # Scrape parts from the component page
                # Look for parts in different ways
                # First try table with headers
                parts_rows = await page.locator("tr:has(td)").all()
                logger.info(f"Found {len(parts_rows)} table rows")

                # Process rows that look like parts
                parts_found = 0
                for row in parts_rows[:10]:  # Limit to 10 parts per component in test mode
                    try:
                        # Extract part data
                        cells = await row.locator("td").all()
                        if len(cells) >= 3:  # At least 3 cells for a part row
                            # Get cell contents
                            cell_texts = []
                            for cell in cells[:4]:  # Get first 4 cells
                                text = await cell.text_content()
                                cell_texts.append(text.strip() if text else "")

                            # Skip header rows
                            if any(header in cell_texts[0].lower() for header in ["ref", "part", "description"]):
                                continue

                            # Assign values based on number of cells
                            if len(cell_texts) >= 4:
                                diagram_ref = cell_texts[0]
                                mpn = cell_texts[1]
                                name = cell_texts[2]
                                price_text = cell_texts[3]
                            elif len(cell_texts) >= 3:
                                diagram_ref = ""
                                mpn = cell_texts[0]
                                name = cell_texts[1]
                                price_text = cell_texts[2]
                            else:
                                continue

                            # Skip if no valid MPN
                            if not mpn or mpn == "-":
                                continue

                            # Parse price
                            price_match = re.search(r"\$?([\d,]+\.?\d*)", price_text or "")
                            price = float(price_match.group(1).replace(",", "")) if price_match else 0.0

                            # Check availability
                            availability = "in_stock"
                            if "backordered" in (price_text or "").lower():
                                availability = "backorder"
                            elif "discontinued" in (price_text or "").lower():
                                availability = "discontinued"

                            # Create part
                            part_data = {
                                "mpn": mpn.strip(),
                                "name": name.strip(),
                                "manufacturer_id": manufacturer_id,
                                "retail_price": price,
                                "category_id": component_category_id,
                                "component_category": component_name,
                                "diagram_reference": diagram_ref.strip(),
                                "availability_status": availability,
                                "model_variant_ids": [variant_id],
                            }

                            part_created = self.create_or_update_part(part_data)
                            if part_created:
                                parts_found += 1

                    except Exception as e:
                        logger.warning(f"Error parsing part row: {e}")

                logger.info(f"Found and processed {parts_found} parts in {component_name}")

        except Exception as e:
            logger.error(f"Error scraping model parts: {e}")
            self.errors.append(f"Model parts: {str(e)}")

    async def run(self, manufacturer_filter: List[str] = None):
        """Run the scraper"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            page = await context.new_page()

            # Process manufacturers
            manufacturers_to_process = manufacturer_filter or list(self.MANUFACTURERS.keys())

            for manufacturer_key in manufacturers_to_process:
                if manufacturer_key in self.MANUFACTURERS:
                    await self.scrape_manufacturer(page, manufacturer_key)

            await browser.close()

        logger.info(f"Scraping complete. Processed {self.processed_parts} parts and {self.processed_variants} model variants")
        if self.errors:
            logger.warning(f"Encountered {len(self.errors)} errors")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Import Crowley Marine parts catalog into Odoo")
    parser.add_argument(
        "--url", default=os.environ.get("ODOO_URL", "http://localhost:8069"), help="Odoo URL (default: http://localhost:8069)"
    )
    parser.add_argument("--db", default=os.environ.get("ODOO_DB", "opw"), help="Odoo database name (default: opw)")
    parser.add_argument("--api-key", default=os.environ.get("ODOO_KEY"), help="Odoo API key")
    parser.add_argument("--manufacturers", help="Comma-separated list of manufacturers to import (default: all)")
    parser.add_argument("--test", action="store_true", help="Run in test mode (limited data)")

    args = parser.parse_args()

    # Check if API key is provided
    if not args.api_key:
        print("ERROR: API key is required. Set ODOO_KEY environment variable or use --api-key")
        sys.exit(1)

    # Parse manufacturers list
    manufacturer_filter = None
    if args.manufacturers:
        manufacturer_filter = [m.strip() for m in args.manufacturers.split(",")]

    # Connect to Odoo
    odoo = OdooConnector(args.url, args.db, args.api_key)
    if not odoo.connect():
        logger.error("Failed to connect to Odoo")
        sys.exit(1)

    # Run scraper
    scraper = CrowleyMarineScraper(odoo)

    try:
        asyncio.run(scraper.run(manufacturer_filter))

        # Print summary
        print("\n=== Import Summary ===")
        print(f"Parts processed: {scraper.processed_parts}")
        print(f"Model variants processed: {scraper.processed_variants}")
        print(f"Errors: {len(scraper.errors)}")

        if scraper.errors:
            print("\nErrors encountered:")
            for error in scraper.errors[:10]:  # Show first 10 errors
                print(f"  - {error}")

    except KeyboardInterrupt:
        logger.info("Import cancelled by user")
    except Exception as e:
        logger.error(f"Import failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
