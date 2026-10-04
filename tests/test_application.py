"""Offline tests for the Flask routes and Mist SDK request boundary."""

import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.pop("MIST_APITOKEN", None)
os.environ.pop("MIST_ORG_ID", None)
os.environ.pop("org_id", None)
os.environ["SECRET_KEY"] = "offline-test-only"

from app import NoGuestPortalSSIDsError
from app import app as flask_app
from mist_connection import (
    MistConnection,
    mac_to_api_format,
    mistapi,
    normalize_mac,
)


class ApplicationRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = flask_app.test_client()

    def test_health_check_includes_utc_timestamp(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "healthy")
        self.assertIsNotNone(datetime.fromisoformat(payload["timestamp"]).tzinfo)

    def test_csv_template_has_header_and_two_examples(self):
        response = self.client.get("/api/csv-template")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.content_type)
        self.assertIn(
            "attachment; filename=guest_import_template.csv",
            response.headers["Content-Disposition"],
        )
        rows = response.get_data(as_text=True).splitlines()
        self.assertEqual(
            rows[0],
            "site_name,ssid,mac,name,email,company,field1,field2,"
            "field3_sponsor_email,minutes",
        )
        self.assertEqual(len(rows), 3)

    def test_authorize_rejects_missing_data_without_api_call(self):
        with patch("app.get_mist_connection") as get_connection:
            response = self.client.post(
                "/api/sites/site-1/wlans/wlan-1/guests", json={}
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "No data provided")
        get_connection.assert_not_called()

    def test_authorize_rejects_missing_mac_without_api_call(self):
        with patch("app.get_mist_connection") as get_connection:
            response = self.client.post(
                "/api/sites/site-1/wlans/wlan-1/guests", json={"name": "Guest"}
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "MAC address is required")
        get_connection.assert_not_called()

    def test_authorize_passes_defaults_and_returns_created_guest(self):
        mist = Mock()
        mist.authorize_guest.return_value = {
            "success": True,
            "guest": {"mac": "aa:bb:cc:dd:ee:ff"},
        }
        with patch("app.get_mist_connection", return_value=mist):
            response = self.client.post(
                "/api/sites/site-1/wlans/wlan-1/guests",
                json={"mac": "AA:BB:CC:DD:EE:FF"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"success": True, "guest": {"mac": "aa:bb:cc:dd:ee:ff"}},
        )
        mist.authorize_guest.assert_called_once_with(
            site_id="site-1",
            wlan_id="wlan-1",
            mac="AA:BB:CC:DD:EE:FF",
            name="",
            email="",
            company="",
            field1="",
            field2="",
            field3="",
            field4="",
            minutes=1440,
            notify=False,
        )

    def test_authorize_returns_client_error_for_api_rejection(self):
        mist = Mock()
        mist.authorize_guest.return_value = {
            "success": False,
            "error": "WLAN rejected the authorization",
        }
        with patch("app.get_mist_connection", return_value=mist):
            response = self.client.post(
                "/api/sites/site-1/wlans/wlan-1/guests",
                json={"mac": "aa:bb:cc:dd:ee:ff"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["error"], "WLAN rejected the authorization"
        )

    def test_authorize_reports_unexpected_failure(self):
        mist = Mock()
        mist.authorize_guest.side_effect = RuntimeError("offline SDK")
        with patch("app.get_mist_connection", return_value=mist):
            response = self.client.post(
                "/api/sites/site-1/wlans/wlan-1/guests",
                json={"mac": "aa:bb:cc:dd:ee:ff"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.get_json()["error"], "offline SDK")

    def test_site_list_reports_missing_guest_portal_configuration(self):
        with patch("app.get_mist_connection") as get_connection:
            get_connection.return_value.get_sites.side_effect = NoGuestPortalSSIDsError(
                "No guest WLANs"
            )
            response = self.client.get("/api/sites")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.get_json(),
            {
                "success": False,
                "error": "No guest WLANs",
                "error_type": "no_guest_portal_ssids",
            },
        )

    def test_bulk_import_validates_required_identifiers(self):
        for body, message in (
            ({"wlan_id": "wlan-1", "mac": "aa:bb:cc:dd:ee:ff"}, "Site not found"),
            ({"site_id": "site-1", "mac": "aa:bb:cc:dd:ee:ff"}, "WLAN not found"),
            ({"site_id": "site-1", "wlan_id": "wlan-1"}, "MAC address is required"),
        ):
            with self.subTest(message=message):
                with patch("app.get_mist_connection") as get_connection:
                    response = self.client.post("/api/bulk-import", json=body)

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["error"], message)
                get_connection.assert_not_called()

    def test_bulk_import_converts_minutes_before_authorization(self):
        mist = Mock()
        mist.authorize_guest.return_value = {"success": True, "guest": {"id": "g-1"}}
        with patch("app.get_mist_connection", return_value=mist):
            response = self.client.post(
                "/api/bulk-import",
                json={
                    "site_id": "site-1",
                    "wlan_id": "wlan-1",
                    "mac": "aa:bb:cc:dd:ee:ff",
                    "minutes": "60",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["guest"], {"id": "g-1"})
        self.assertEqual(mist.authorize_guest.call_args.kwargs["minutes"], 60)

    def test_search_passes_query_and_returns_clients(self):
        mist = Mock()
        mist.search_wireless_clients.return_value = [{"mac": "aa:bb:cc:dd:ee:ff"}]
        with patch("app.get_mist_connection", return_value=mist):
            response = self.client.get("/api/sites/site-1/clients/search?query=printer")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["clients"], [{"mac": "aa:bb:cc:dd:ee:ff"}])
        mist.search_wireless_clients.assert_called_once_with("site-1", "printer")


class MistConnectionTests(unittest.TestCase):
    def test_updated_sdk_exposes_all_application_api_methods(self):
        endpoints = (
            (mistapi, "APISession"),
            (mistapi, "get_all"),
            (mistapi.api.v1.self.self, "getSelf"),
            (mistapi.api.v1.orgs.orgs, "getOrg"),
            (mistapi.api.v1.orgs.sites, "listOrgSites"),
            (mistapi.api.v1.orgs.wlans, "listOrgWlans"),
            (mistapi.api.v1.orgs.templates, "getOrgTemplate"),
            (mistapi.api.v1.orgs.sitegroups, "getOrgSiteGroup"),
            (mistapi.api.v1.orgs.guests, "listOrgGuestAuthorizations"),
            (mistapi.api.v1.orgs.guests, "updateOrgGuestAuthorization"),
            (mistapi.api.v1.sites.wlans, "listSiteWlans"),
            (mistapi.api.v1.sites.guests, "listSiteAllGuestAuthorizations"),
            (mistapi.api.v1.sites.guests, "updateSiteGuestAuthorization"),
            (mistapi.api.v1.sites.stats, "listSiteWirelessClientsStats"),
        )

        for namespace, method in endpoints:
            with self.subTest(method=method):
                self.assertTrue(callable(getattr(namespace, method, None)))

    def test_normalize_mac_accepts_supported_separators(self):
        for mac in (
            "AA:BB:CC:DD:EE:FF",
            "AA-BB-CC-DD-EE-FF",
            "aabb.ccdd.eeff",
            "aabbccddeeff",
        ):
            with self.subTest(mac=mac):
                self.assertEqual(normalize_mac(mac), "aa:bb:cc:dd:ee:ff")

    def test_mac_helpers_reject_wrong_length_and_non_hex(self):
        for mac in ("aa:bb:cc:dd:ee", "aa:bb:cc:dd:ee:gg"):
            with self.subTest(mac=mac):
                with self.assertRaises(ValueError):
                    normalize_mac(mac)
                with self.assertRaises(ValueError):
                    mac_to_api_format(mac)

    def test_api_mac_format_omits_separators(self):
        self.assertEqual(mac_to_api_format("AA-BB-CC-DD-EE-FF"), "aabbccddeeff")

    def test_authorize_uses_normalized_mac_and_server_owned_token_field(self):
        endpoint = Mock()
        fake_api = SimpleNamespace(
            v1=SimpleNamespace(
                sites=SimpleNamespace(
                    guests=SimpleNamespace(
                        updateSiteGuestAuthorization=endpoint,
                    )
                )
            )
        )
        connection = MistConnection()
        session = object()
        connection._get_session = Mock(return_value=session)
        connection.get_token_name = Mock(return_value="Offline test token")

        with (
            patch("mist_connection.mistapi", SimpleNamespace(api=fake_api)),
            patch("mist_connection.time.time", return_value=1_700_000_000),
        ):
            result = connection.authorize_guest(
                site_id="site-1",
                wlan_id="wlan-1",
                mac="AA-BB-CC-DD-EE-FF",
                name="Guest",
                minutes=1,
                field4="client-controlled value",
            )

        self.assertTrue(result["success"])
        guest = result["guest"]
        self.assertEqual(guest["mac"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(guest["authorized_expiring_time"], 1_700_000_060)
        endpoint.assert_called_once_with(
            session,
            "site-1",
            "aa:bb:cc:dd:ee:ff",
            body={
                "mac": "aa:bb:cc:dd:ee:ff",
                "minutes": 1,
                "authorized": True,
                "name": "Guest",
                "field4": "Offline test token",
                "wlan_id": "wlan-1",
            },
        )

    def test_invalid_mac_is_rejected_before_sdk_call(self):
        endpoint = Mock()
        fake_api = SimpleNamespace(
            v1=SimpleNamespace(
                sites=SimpleNamespace(
                    guests=SimpleNamespace(updateSiteGuestAuthorization=endpoint)
                )
            )
        )
        connection = MistConnection()
        connection._get_session = Mock(return_value=object())

        with patch("mist_connection.mistapi", SimpleNamespace(api=fake_api)):
            result = connection.authorize_guest("site-1", "wlan-1", "invalid")

        self.assertFalse(result["success"])
        self.assertIn("Invalid MAC address", result["error"])
        endpoint.assert_not_called()


if __name__ == "__main__":
    unittest.main()
