import sys, os, json, asyncio

# allow running from project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from crawler import crawl_portal

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_portal.py \"Portal Name\"")
        print("Available portals from config.json:")
        with open(os.path.join(os.path.dirname(__file__), "..", "config.json")) as f:
            cfg = json.load(f)
        for p in cfg.get("portals", []):
            print(" -", p.get("name"))
        return

    portal_name = sys.argv[1]
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.json")
    with open(cfg_path) as f:
        cfg = json.load(f)

    portal = None
    for p in cfg.get("portals", []):
        if p.get("name") == portal_name:
            portal = p
            break

    if not portal:
        print("Portal not found in config.json:", portal_name)
        return

    print("Starting crawl for portal:", portal_name)
    asyncio.run(crawl_portal(portal))

if __name__ == "__main__":
    main()

