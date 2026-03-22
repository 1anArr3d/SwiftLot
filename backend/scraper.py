import asyncio
import json
import sqlite3
from playwright.async_api import async_playwright

BASE_URL = "https://app.marketplace.autura.com"
PARALLEL_PAGES = 5  # number of vehicle pages to scrape simultaneously

def init_db():
    with sqlite3.connect('swiftlot.db') as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS vehicles (
            vin TEXT PRIMARY KEY, year TEXT, make TEXT, model TEXT, color TEXT,
            key_status TEXT, catalytic_converter TEXT, start_status TEXT,
            engine_type TEXT, transmission TEXT, auction_id TEXT, city TEXT,
            last_recorded_odo TEXT, images TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS odometer_history (
            row_id TEXT PRIMARY KEY, vin TEXT, inspection_date TEXT, mileage INTEGER)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS watchlist (
            vin TEXT PRIMARY KEY, year TEXT, make TEXT, model TEXT, color TEXT,
            key_status TEXT, catalytic_converter TEXT, start_status TEXT,
            engine_type TEXT, transmission TEXT, auction_id TEXT, city TEXT,
            last_recorded_odo TEXT, images TEXT, liked_at TEXT)''')
        # migrate existing DBs that don't have the images column yet
        try:
            conn.execute("ALTER TABLE vehicles ADD COLUMN images TEXT")
        except Exception:
            pass

def save_vehicle(conn, vehicle, auction_id, city, images_json):
    raw_odo = vehicle.get("Odometer") or vehicle.get("Odometer Reading") or vehicle.get("Miles")
    listing_odo = raw_odo.split(" (")[0].strip() if raw_odo else None
    data = (
        vehicle.get("VIN"), vehicle.get("Year"), vehicle.get("Make"),
        vehicle.get("Model"), vehicle.get("Color"), vehicle.get("Key status"),
        vehicle.get("Catalytic Converter"), vehicle.get("Start status"),
        vehicle.get("Engine type"), vehicle.get("Transmission"),
        str(auction_id), city, listing_odo, images_json
    )
    conn.execute('''
        INSERT INTO vehicles (vin, year, make, model, color, key_status,
        catalytic_converter, start_status, engine_type, transmission, auction_id, city, last_recorded_odo, images)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(vin) DO UPDATE SET auction_id=excluded.auction_id, images=excluded.images
    ''', data)

async def scrape_vehicle(browser, href, auctionid, city, conn, lock):
    page = await browser.new_page()
    try:
        await page.goto(f"{BASE_URL}{href}", wait_until="load")
        table = await page.wait_for_selector("div.ant-table-content", timeout=10000)
        rows = await table.query_selector_all("tr")
        vehicle_data = {}
        for r in rows:
            cells = await r.query_selector_all("td")
            if len(cells) >= 2:
                key = (await cells[0].inner_text()).strip()
                val = (await cells[1].inner_text()).strip()
                vehicle_data[key] = val

        # extract image URLs from gallery-thumb background-image styles
        image_urls = await page.evaluate("""
            () => Array.from(document.querySelectorAll('div.gallery-thumb'))
                .map(el => {
                    const style = el.getAttribute('style') || '';
                    const match = style.match(/url\\(["']?(.*?)["']?\\)/);
                    return match ? match[1].replace('thumbnail_4x3', 'full_4x3') : null;
                })
                .filter(Boolean)
        """)
        images_json = json.dumps(image_urls)

        if "VIN" in vehicle_data:
            async with lock:
                save_vehicle(conn, vehicle_data, auctionid, city, images_json)
                conn.commit()
    except Exception as e:
        print(f"Error scraping {href}: {e}")
    finally:
        await page.close()

async def _scrape(auctionid, city):
    with sqlite3.connect('swiftlot.db') as conn:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(f"{BASE_URL}/auction/{city}/auction-{auctionid}", wait_until="load")
                await page.wait_for_selector('a[href*="/vehicle/"]', timeout=10000)

                # scroll until no new links appear
                prev_count = 0
                while True:
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1500)
                    links = [await l.get_attribute("href") for l in await page.query_selector_all('a[href*="/vehicle/"]')]
                    if len(links) == prev_count:
                        break
                    prev_count = len(links)

                await page.close()
                print(f"Found {len(set(links))} vehicles")

                # scrape all vehicle pages in parallel batches
                lock = asyncio.Lock()
                sem = asyncio.Semaphore(PARALLEL_PAGES)

                async def bounded(href):
                    async with sem:
                        await scrape_vehicle(browser, href, auctionid, city, conn, lock)

                await asyncio.gather(*[bounded(href) for href in set(links)])
            except Exception as e:
                print(f"Error: {e}")
            finally:
                await browser.close()

def scrape_data(auctionid, city="SA-TX"):
    asyncio.run(_scrape(auctionid, city))
