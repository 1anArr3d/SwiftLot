import sqlite3
from playwright.sync_api import sync_playwright

DB_PATH = 'swiftlot.db'

def save_history(vin, results):
    if not results: return
    with sqlite3.connect(DB_PATH) as conn:
        for i, res in enumerate(results):
            conn.execute('INSERT OR REPLACE INTO odometer_history VALUES (?, ?, ?, ?)',
                         (f"{vin}_{i}", vin, res['date'], res['odometer']))

        display = "\n".join([f"{r['date']}: {r['odometer']:,}" for r in results])
        conn.execute("UPDATE vehicles SET last_recorded_odo = ? WHERE vin = ?", (display, vin))

def run_inspection_scrape(vin):
    sel = "a[onclick*='DoSelect']"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        page = browser.new_page()
        try:
            # Entry via VehicleTestDetail establishes the correct session state
            page.goto("https://www.mytxcar.org/TXCar_Net/VehicleTestDetail.aspx", timeout=60000)
            page.wait_for_function("document.querySelector('[name=\"cf-turnstile-response\"]').value.length > 0")
            page.locator('input[type="submit"]').click()

            page.wait_for_selector("#txtVin", timeout=15000)
            page.locator("#txtVin").fill(vin)
            page.locator('input[title="Search"]').click()
            page.wait_for_selector(sel, timeout=10000)

            if not page.locator(sel).count():
                print(f"No inspection records found for VIN: {vin}")
                return

            results, seen_years = [], set()
            while len(results) < 3:
                # Re-read rows fresh from the live page each iteration
                rows = page.evaluate("""
                    () => Array.from(document.querySelectorAll('a[onclick*="DoSelect"]')).map(a => ({
                        date: a.getAttribute('aria-label').split(' Click')[0].split(' ')[0],
                        idx: Array.from(document.querySelectorAll('a[onclick*="DoSelect"]')).indexOf(a)
                    }))
                """)

                target = next(
                    (r for r in rows if r['date'].split('/')[-1] not in seen_years),
                    None
                )
                if not target:
                    break

                year = target['date'].split('/')[-1].split(' ')[0][:4]
                seen_years.add(year)

                with page.expect_navigation(wait_until="domcontentloaded"):
                    page.locator(sel).nth(target['idx']).click()

                try:
                    page.wait_for_selector("td:has-text('Odometer')", timeout=10000)
                    miles = page.locator("td:has-text('Odometer') + td").inner_text().strip()
                except:
                    miles = ""

                with page.expect_navigation(wait_until="domcontentloaded"):
                    page.locator("#btnBack").click()
                page.wait_for_selector(sel, timeout=10000)

                if not miles:
                    continue
                results.append({"date": target['date'], "odometer": int(miles.replace(',', ''))})

            save_history(vin, results)
            print(f"Saved {len(results)} records for {vin}")

        except Exception as e:
            print(f"Inspection scrape error for {vin}: {e}")
        finally:
            try: browser.close()
            except: pass
