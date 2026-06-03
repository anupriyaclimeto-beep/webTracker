#!/usr/bin/env python
"""
Test crawler locally to debug issues before GitHub Actions
"""
import sys
import os
import json
import asyncio
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from storage import init_db
from crawler import crawl_portal

async def test_portal(portal_name):
    """Test a single portal crawl"""
    try:
        init_db()
        
        with open("config.json") as f:
            config = json.load(f)
        
        # Find the portal
        portal = None
        for p in config.get("portals", []):
            if p.get("name") == portal_name:
                portal = p
                break
        
        if not portal:
            logger.error(f"❌ Portal '{portal_name}' not found in config.json")
            logger.info("Available portals:")
            for p in config.get("portals", []):
                logger.info(f"  - {p.get('name')}")
            return False
        
        logger.info(f"✅ Testing portal: {portal_name}")
        logger.info(f"   URL: {portal.get('url')}")
        logger.info(f"   Auth: {portal.get('auth', 'none')}")
        
        # Run crawler
        await crawl_portal(portal)
        logger.info(f"✅ {portal_name} completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ {portal_name} failed: {e}", exc_info=True)
        return False

async def test_all_portals():
    """Test all portals"""
    try:
        init_db()
        
        with open("config.json") as f:
            config = json.load(f)
        
        portals = config.get("portals", [])
        if not portals:
            logger.error("❌ No portals configured in config.json")
            return
        
        logger.info(f"Testing {len(portals)} portals...")
        results = {}
        
        for idx, portal in enumerate(portals, 1):
            name = portal.get("name")
            logger.info(f"\n[{idx}/{len(portals)}] {name}")
            try:
                await crawl_portal(portal)
                results[name] = "✅ OK"
                logger.info(f"✅ {name} complete")
            except Exception as e:
                results[name] = f"❌ {str(e)[:100]}"
                logger.error(f"❌ {name} failed: {e}")
        
        logger.info("\n" + "="*60)
        logger.info("SUMMARY:")
        logger.info("="*60)
        for name, status in results.items():
            logger.info(f"{name}: {status}")
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Test single portal: python test_crawler.py "EPR PLASTIC"
        portal_name = sys.argv[1]
        success = asyncio.run(test_portal(portal_name))
        sys.exit(0 if success else 1)
    else:
        # Test all portals
        asyncio.run(test_all_portals())
