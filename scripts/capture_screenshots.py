import time
from playwright.sync_api import sync_playwright

BASE_URL = "https://interview.daruntech.cloud"

def capture():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        
        # 1. Login Page Screenshot
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{BASE_URL}/auth/login", wait_until="networkidle")
        time.sleep(1)
        page.screenshot(path="docs/screenshots/01_login_page.png")
        print("Captured 01_login_page.png")

        # 2. Student Login & Dashboard
        page.fill('input[name="username"]', "student")
        page.fill('input[name="password"]', "student")
        page.click('button[type="submit"]')
        page.wait_for_url("**/student**", timeout=10000)
        time.sleep(2)
        page.screenshot(path="docs/screenshots/02_student_dashboard.png")
        print("Captured 02_student_dashboard.png")

        # 3. Student Interview Setup / Room
        try:
            # Check for interview button or navigate to /student/interview
            page.goto(f"{BASE_URL}/student/interview", wait_until="networkidle")
            time.sleep(2)
            page.screenshot(path="docs/screenshots/03_student_interview.png")
            print("Captured 03_student_interview.png")
        except Exception as e:
            print("Could not capture interview screen:", e)

        # 4. Admin Context (New incognito context)
        admin_context = browser.new_context(viewport={"width": 1440, "height": 900})
        admin_page = admin_context.new_page()
        admin_page.goto(f"{BASE_URL}/auth/login", wait_until="networkidle")
        admin_page.fill('input[name="username"]', "admin")
        admin_page.fill('input[name="password"]', "admin")
        admin_page.click('button[type="submit"]')
        admin_page.wait_for_url("**/admin**", timeout=10000)
        time.sleep(2)
        admin_page.screenshot(path="docs/screenshots/04_admin_dashboard.png")
        print("Captured 04_admin_dashboard.png")

        # 5. Admin Question Banks
        try:
            admin_page.goto(f"{BASE_URL}/admin/banks", wait_until="networkidle")
            time.sleep(2)
            admin_page.screenshot(path="docs/screenshots/05_admin_question_banks.png")
            print("Captured 05_admin_question_banks.png")
        except Exception as e:
            print("Could not capture banks screen:", e)

        browser.close()
        print("All screenshots captured successfully!")

if __name__ == "__main__":
    capture()
