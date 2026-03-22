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


CARD_JS = """
    () => Array.from(document.querySelectorAll('[data-testid="auction-card-item"]'))
        .map(el => {
            const calendarLi = el.querySelector('.anticon-calendar')?.closest('li');
            return {
                auction_id:      el.getAttribute('data-auctionid').replace('auction-', ''),
                region_id:       el.getAttribute('data-regionid'),
                auction_status:  el.getAttribute('data-auction-status'),
                vehicles_listed: parseInt(el.getAttribute('data-vehicles-listed') || '0'),
                seller_name:     el.querySelector('.ant-card-meta-title span')?.innerText?.trim() || '',
                auction_date:    calendarLi ? calendarLi.innerText.trim() : ''
            };
        })
"""


async def _scrape_page(page, url: str, label: str) -> list[dict]:
    await page.goto(url, wait_until="load")
    try:
        await page.wait_for_selector('[data-testid="auction-card-item"]', timeout=15000)
    except Exception:
        print(f"[discovery] No auction cards found for {label}")
        return []

    prev = 0
    while True:
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)
        count = await page.locator('[data-testid="auction-card-item"]').count()
        if count == prev:
            break
        prev = count

    return await page.evaluate(CARD_JS)


async def _get_all_auctions(page, state: str, region_id: str = None) -> list[dict]:
    all_auctions = await _scrape_page(page, f"{BASE_URL}/auctions/by-state/{state}", state)

    if region_id:
        all_auctions = [a for a in all_auctions if a['region_id'] == region_id]

    with_vehicles = [a for a in all_auctions if a['vehicles_listed'] > 0]
    label = region_id or state
    print(f"[discovery] {len(all_auctions)} total cards for {label}, {len(with_vehicles)} with vehicles")
    return with_vehicles


async def _run_discovery(state: str = "TX", region_id: str = None):
    init_db()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            label = region_id or state
            print(f"[discovery] Fetching auctions for {label}...")
            auctions = await _get_all_auctions(page, state, region_id)

            all_seen_ids = set()

            with sqlite3.connect(DB_PATH) as conn:
                for a in auctions:
                    upsert_auction(conn, a)
                    all_seen_ids.add(a['auction_id'])

                conn.commit()

                if all_seen_ids:
                    mark_completed_auctions(conn, all_seen_ids)
                    conn.commit()

            print(f"[discovery] Saved {len(auctions)} auctions.")

        except Exception as e:
            print(f"[discovery] Error: {e}")
        finally:
            await browser.close()

    print("[discovery] Done.")


def run_discovery(state: str = "TX", region_id: str = None):
    asyncio.run(_run_discovery(state, region_id))


if __name__ == "__main__":
    run_discovery()
