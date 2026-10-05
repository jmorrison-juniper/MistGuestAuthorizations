"""Capture the real Flask UI with offline Mist fixtures."""

import os
import threading
from pathlib import Path
from unittest.mock import Mock, patch

from playwright.sync_api import Page, Route, sync_playwright
from werkzeug.serving import make_server

OUTPUT = Path(__file__).parent / "screenshots"
CSV_EXAMPLE = (
    "site_name,ssid,mac,name,email,company,field1,field2,field3_sponsor_email,minutes\n"
    "Example Lab,Guest WiFi,02:00:00:00:00:03,Demo Display,display@example.com,"
    "Example Company,Lobby,Display,sponsor@example.com,1440\n"
)


def offline_connection(connection_type):
    guests = [
        {
            "mac": "02:00:00:00:00:01",
            "name": "Demo Printer",
            "email": "printer@example.com",
            "company": "Example Company",
            "field1": "Asset 001",
            "field2": "Reception",
            "field3": "sponsor@example.com",
            "field4": "Offline fixture token",
            "remaining_minutes": 1440,
            "is_expired": False,
            "wlan_id": "demo-wlan",
        }
    ]
    mist = Mock(spec=connection_type)
    mist.test_connection.return_value = {"success": True, "org_name": "Offline Demo"}
    mist.get_sites.return_value = [
        {"id": "demo-site", "name": "Example Lab", "address": "Fictional location"}
    ]
    mist.get_guest_wlans.return_value = [
        {"id": "demo-wlan", "ssid": "Guest WiFi", "is_org_wlan": False}
    ]
    mist.get_wlan_guests.return_value = guests
    mist.search_wireless_clients.return_value = [
        {
            "mac": "02:00:00:00:00:02",
            "hostname": "demo-display",
            "ip": "192.0.2.2",
            "ssid": "Guest WiFi",
        }
    ]

    def authorize(**fields):
        guest = {
            **fields,
            "field4": "Offline fixture token",
            "remaining_minutes": fields["minutes"],
            "is_expired": False,
        }
        guests.append(guest)
        return {"success": True, "guest": guest}

    mist.authorize_guest.side_effect = authorize
    return mist


def save_screen(page: Page, filename: str, full_page: bool = False) -> None:
    page.evaluate("""async () => {
            await document.fonts.ready;
            await Promise.all(document.getAnimations()
                .filter(animation => animation.effect.getComputedTiming().iterations !== Infinity)
                .map(animation => animation.finished));
        }""")
    page.screenshot(path=str(OUTPUT / filename), full_page=full_page)


def capture_user_screens(page: Page, base_url: str) -> None:
    page.goto(base_url)
    page.locator("#siteSelector option[value='demo-site']").wait_for(state="attached")
    page.select_option("#siteSelector", "demo-site")
    page.locator("#wlanSelector option[value='demo-wlan']").wait_for(state="attached")
    page.select_option("#wlanSelector", "demo-wlan")
    page.get_by_text("Demo Printer", exact=True).wait_for()
    save_screen(page, "01-main-dashboard.png", full_page=True)

    page.get_by_text("Demo Printer", exact=True).click()
    page.locator("#editGuestModal").wait_for(state="visible")
    save_screen(page, "02-edit-guest.png")
    page.locator("#editGuestModal [data-bs-dismiss='modal']").first.click()
    page.locator("#editGuestModal").wait_for(state="hidden")

    page.click("#addGuestBtn")
    page.locator("#addGuestModal").wait_for(state="visible")
    save_screen(page, "03-add-guest-blank.png")
    page.fill("#guestMac", "02:00:00:00:00:02")
    page.fill("#guestName", "Demo Display")
    page.fill("#guestEmail", "display@example.com")
    page.fill("#guestCompany", "Example Company")
    page.fill("#guestField1", "Asset 002")
    page.fill("#guestField2", "Meeting room")
    page.fill("#guestField3", "sponsor@example.com")
    save_screen(page, "04-add-guest-filled.png")
    page.click("#submitGuestBtn")
    page.locator("#addGuestModal").wait_for(state="hidden")
    page.locator("#guestList").get_by_text("Demo Display", exact=True).wait_for()
    page.locator("#toastContainer .toast-notification").wait_for(state="hidden")
    save_screen(page, "05-guest-added.png", full_page=True)

    page.click("#bulkImportBtn")
    page.locator("#bulkImportModal").wait_for(state="visible")
    save_screen(page, "06-bulk-import.png")
    page.set_input_files(
        "#csvFileInput",
        {
            "name": "offline-guests.csv",
            "mimeType": "text/csv",
            "buffer": CSV_EXAMPLE.encode(),
        },
    )
    page.locator("#csvPreview").wait_for(state="visible")
    save_screen(page, "07-csv-example.png")


def capture():
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    import app as application

    OUTPUT.mkdir(exist_ok=True)
    mist = offline_connection(application.MistConnection)
    with (
        patch.object(application, "get_mist_connection", return_value=mist),
        patch.object(
            application.MistConnection,
            "_get_session",
            side_effect=AssertionError(
                "Live Mist sessions are forbidden during capture"
            ),
        ),
    ):
        server = make_server("127.0.0.1", 0, application.app)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as playwright:
                executable = os.getenv("SCREENSHOT_BROWSER")
                browser = playwright.chromium.launch(
                    executable_path=executable, headless=True
                )
                page = browser.new_page(viewport={"width": 1440, "height": 1080})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))

                def restrict_requests(route: Route):
                    if route.request.url.startswith(
                        (base_url + "/", "https://cdn.jsdelivr.net/")
                    ):
                        route.continue_()
                    else:
                        errors.append(
                            f"Unexpected network request: {route.request.url}"
                        )
                        route.abort()

                page.route("**/*", restrict_requests)
                capture_user_screens(page, base_url)
                browser.close()
                if errors:
                    raise RuntimeError("\n".join(errors))
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    capture()
