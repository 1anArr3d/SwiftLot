import asyncio
import sqlite3
from datetime import datetime, timezone
from playwright.async_api import async_playwright

BASE_URL = "https://app.marketplace.autura.com"
DB_PATH = "swiftlot.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS auctions (
            auction_id   TEXT PRIMARY KEY,
            region_id    TEXT,
            seller_name  TEXT,
            auction_status TEXT,
            vehicles_listed INTEGER,
            auction_date TEXT,
            last_discovered TEXT,
            last_scraped_count INTEGER
        )''')
        try:
            conn.execute("ALTER TABLE auctions ADD COLUMN last_scraped_count INTEGER")
        except Exception:
            pass


def upsert_auction(conn, auction):
    conn.execute('''
        INSERT INTO auctions
            (auction_id, region_id, seller_name, auction_status, vehicles_listed, auction_date, last_discovered)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(auction_id) DO UPDATE SET
            auction_status  = excluded.auction_status,
            vehicles_listed = excluded.vehicles_listed,
            auction_date    = excluded.auction_date,
            last_discovered = excluded.last_discovered
    ''', (
        auction['auction_id'],
        auction['region_id'],
        auction['seller_name'],
        auction['auction_status'],
        auction['vehicles_listed'],
        auction['auction_date'],
        datetime.now(timezone.utc).isoformat(),
    ))


def mark_completed_auctions(conn, seen_ids: set):
    """Any auction not seen in the latest discovery run gets marked completed."""
    placeholders = ','.join('?' * len(seen_ids))
    conn.execute(
        f"UPDATE auctions SET auction_status='completed' WHERE auction_id NOT IN ({placeholders})",
        list(seen_ids)
    )


STATE_CARD_JS = """
    () => Array.from(document.querySelectorAll('[data-testid="auction-card-item"]'))
        .map(el => ({
            auction_id: el.getAttribute('data-auctionid').replace('auction-', ''),
            region_id:  el.getAttribute('data-regionid'),
        }))
"""

CITY_CARD_JS = """
    () => {
        const results = [];
        const sections = Array.from(document.querySelectorAll('.section-upcoming'));
        document.querySelectorAll('[data-testid="auction-card-item"]').forEach(el => {
            let seller = '';
            for (let i = sections.length - 1; i >= 0; i--) {
                if (sections[i].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) {
                    const a = sections[i].querySelector('a[href*="/auctions/series/"]');
                    if (a) { seller = a.innerText.trim(); }
                    break;
                }
            }
            const calendarLi = el.querySelector('.anticon-calendar')?.closest('li');
            results.push({
                auction_id:      el.getAttribute('data-auctionid').replace('auction-', ''),
                region_id:       el.getAttribute('data-regionid'),
                auction_status:  el.getAttribute('data-auction-status'),
                vehicles_listed: parseInt(el.getAttribute('data-vehicles-listed') || '0'),
                seller_name:     seller,
                auction_date:    calendarLi ? calendarLi.innerText.trim() : ''
            });
        });
        return results;
    }
"""


async def _scroll_to_end(page):
    prev = 0
    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)
        count = await page.locator('[data-testid="auction-card-item"]').count()
        if count == prev:
            break
        prev = count


async def _run_discovery(state: str = "TX", region_id: str = None):
    init_db()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            # Phase 1: get region_ids from by-state page
            print(f"[discovery] Fetching region IDs for {state}...")
            await page.goto(f"{BASE_URL}/auctions/by-state/{state}", wait_until="load")
            try:
                await page.wait_for_selector('[data-testid="auction-card-item"]', timeout=15000)
            except Exception:
                print(f"[discovery] No cards on by-state/{state} page")
                return
            await _scroll_to_end(page)
            state_cards = await page.evaluate(STATE_CARD_JS)
            region_ids = sorted(set(c['region_id'] for c in state_cards if c['region_id']))
            if region_id:
                region_ids = [r for r in region_ids if r == region_id]
            print(f"[discovery] Regions: {region_ids}")

            # Phase 2: scrape each city page for full auction list
            all_auctions = []
            for rid in region_ids:
                url = f"{BASE_URL}/auctions/{rid}"
                await page.goto(url, wait_until="load")
                try:
                    await page.wait_for_selector('[data-testid="auction-card-item"]', timeout=15000)
                except Exception:
                    print(f"[discovery] [{rid}] No cards found")
                    continue
                await _scroll_to_end(page)
                cards = await page.evaluate(CITY_CARD_JS)
                print(f"[discovery] [{rid}] {len(cards)} cards")
                all_auctions.extend(cards)

            with_vehicles = [a for a in all_auctions if a['vehicles_listed'] > 0]
            print(f"[discovery] {len(all_auctions)} total, {len(with_vehicles)} with vehicles")

            all_seen_ids = set()
            with sqlite3.connect(DB_PATH) as conn:
                for a in with_vehicles:
                    upsert_auction(conn, a)
                    all_seen_ids.add(a['auction_id'])
                conn.commit()
                if all_seen_ids:
                    mark_completed_auctions(conn, all_seen_ids)
                    conn.commit()

            print(f"[discovery] Saved {len(with_vehicles)} auctions.")

        except Exception as e:
            print(f"[discovery] Error: {e}")
        finally:
            await browser.close()

    print("[discovery] Done.")


def run_discovery(state: str = "TX", region_id: str = None):
    asyncio.run(_run_discovery(state, region_id))


if __name__ == "__main__":
    run_discovery()
