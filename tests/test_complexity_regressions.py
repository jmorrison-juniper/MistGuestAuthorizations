"""Offline behavioral coverage for the complexity refactor in issue #15."""

import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.pop("MIST_APITOKEN", None)
os.environ.pop("MIST_ORG_ID", None)
os.environ.pop("org_id", None)

from mist_connection import (
    UPDATE_FAILED_MESSAGE,
    MistConnection,
    NoGuestPortalSSIDsError,
)


class SiteDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.connection = MistConnection()
        self.connection.org_id = "org-1"
        self.session = object()
        self.connection._get_session = Mock(return_value=self.session)
        self.stack = self.enterContext(ExitStack())
        self.sites = self.stack.enter_context(
            patch("mist_connection.mistapi.api.v1.orgs.sites.listOrgSites")
        )
        self.wlans = self.stack.enter_context(
            patch("mist_connection.mistapi.api.v1.orgs.wlans.listOrgWlans")
        )
        self.templates = self.stack.enter_context(
            patch("mist_connection.mistapi.api.v1.orgs.templates.getOrgTemplate")
        )
        self.groups = self.stack.enter_context(
            patch("mist_connection.mistapi.api.v1.orgs.sitegroups.getOrgSiteGroup")
        )
        self.stack.enter_context(
            patch(
                "mist_connection.mistapi.get_all",
                side_effect=lambda response, **_kwargs: response.data,
            )
        )
        self.sites.return_value = SimpleNamespace(
            data=[
                {"id": "site-2", "name": "zebra", "address": "Example"},
                {"id": "site-1", "name": "Alpha"},
                {"id": "site-3"},
            ]
        )
        self.wlans.return_value = SimpleNamespace(data=[])

    @staticmethod
    def guest_wlan(**scope):
        return {"portal": {"enabled": True}, **scope}

    def test_unfiltered_sites_are_sorted_and_formatted_without_wlan_lookup(self):
        sites = self.connection.get_sites(filter_guest_wlans=False)
        self.assertEqual([site["id"] for site in sites], ["site-3", "site-1", "site-2"])
        self.assertEqual(
            sites[0],
            {
                "id": "site-3",
                "name": "Unknown",
                "address": "",
                "country_code": "",
                "timezone": "",
            },
        )
        self.wlans.assert_not_called()
        self.sites.assert_called_once_with(self.session, "org-1", limit=1000)

    def test_all_sites_scope_and_disabled_portals(self):
        for excluded in ({"portal": {"enabled": False}}, {"enabled": False}):
            with self.subTest(excluded=excluded):
                self.wlans.return_value.data = [
                    self.guest_wlan(apply_to="all", **excluded)
                ]
                with self.assertRaises(NoGuestPortalSSIDsError):
                    self.connection.get_sites()
        self.wlans.return_value.data = [self.guest_wlan(apply_to="all")]
        self.assertEqual(len(self.connection.get_sites()), 3)
        self.templates.assert_not_called()
        self.groups.assert_not_called()

    def test_template_and_direct_scopes_share_sitegroup_cache(self):
        self.wlans.return_value.data = [
            self.guest_wlan(template_id="template-1"),
            self.guest_wlan(template_id="template-1"),
            self.guest_wlan(site_ids=["site-2"], sitegroup_ids=["group-1"]),
        ]
        self.templates.return_value = SimpleNamespace(
            data={"applies": {"site_ids": ["site-1"], "sitegroup_ids": ["group-1"]}}
        )
        self.groups.return_value = SimpleNamespace(data={"site_ids": ["site-2"]})
        sites = self.connection.get_sites()
        self.assertEqual([site["id"] for site in sites], ["site-1", "site-2"])
        self.templates.assert_called_once_with(self.session, "org-1", "template-1")
        self.groups.assert_called_once_with(self.session, "org-1", "group-1")

    def test_null_assignments_and_unknown_sites_do_not_include_unassigned_sites(self):
        self.wlans.return_value.data = [
            self.guest_wlan(site_ids=None, sitegroup_ids=None),
            self.guest_wlan(site_ids=["unknown-site"]),
            self.guest_wlan(template_id="template-1"),
        ]
        self.templates.return_value = SimpleNamespace(
            data={"applies": {"site_ids": None, "sitegroup_ids": None}}
        )
        with self.assertRaises(NoGuestPortalSSIDsError):
            self.connection.get_sites()

    def test_failed_lookups_are_cached_and_other_assignments_survive(self):
        self.wlans.return_value.data = [
            self.guest_wlan(template_id="broken"),
            self.guest_wlan(template_id="broken"),
            self.guest_wlan(site_ids=["site-1"], sitegroup_ids=["broken"]),
            self.guest_wlan(sitegroup_ids=["broken"]),
        ]
        self.templates.side_effect = RuntimeError("offline template failure")
        self.groups.side_effect = RuntimeError("offline sitegroup failure")
        with self.assertLogs("mist_connection", level="DEBUG"):
            sites = self.connection.get_sites()
        self.assertEqual([site["id"] for site in sites], ["site-1"])
        self.assertEqual(self.templates.call_count, 1)
        self.assertEqual(self.groups.call_count, 1)

    def test_org_wlan_failure_is_logged_and_reports_no_guest_portal(self):
        self.wlans.side_effect = RuntimeError("offline WLAN failure")
        with (
            self.assertLogs("mist_connection", level="WARNING") as logs,
            self.assertRaises(NoGuestPortalSSIDsError),
        ):
            self.connection.get_sites()
        self.assertIn("offline WLAN failure", "\n".join(logs.output))

    def test_site_list_failure_is_propagated(self):
        self.sites.side_effect = RuntimeError("offline sites failure")
        with self.assertRaisesRegex(RuntimeError, "offline sites failure"):
            self.connection.get_sites()

    def test_missing_resource_data_and_empty_sitegroups_are_tolerated(self):
        self.wlans.return_value.data = [
            self.guest_wlan(template_id="missing-data"),
            self.guest_wlan(sitegroup_ids=["empty-group"]),
            self.guest_wlan(site_ids=["site-1"]),
        ]
        self.templates.return_value = object()
        for response in (object(), SimpleNamespace(data={"site_ids": None})):
            with self.subTest(response=response):
                self.groups.return_value = response
                sites = self.connection.get_sites()
                self.assertEqual([site["id"] for site in sites], ["site-1"])

    def test_org_discovery_success_and_failure(self):
        self.connection.org_id = None
        self.connection.test_connection = Mock(return_value={"success": False})
        with self.assertRaisesRegex(ValueError, "Could not determine organization"):
            self.connection.get_sites()
        self.sites.assert_not_called()

        def discover_org():
            self.connection.org_id = "discovered-org"
            return {"success": True}

        self.connection.test_connection.side_effect = discover_org
        self.connection.get_sites(filter_guest_wlans=False)
        self.sites.assert_called_once_with(self.session, "discovered-org", limit=1000)


class GuestUpdateTests(unittest.TestCase):
    def setUp(self):
        self.connection = MistConnection()
        self.connection.org_id = "org-1"
        self.session = object()
        self.connection._get_session = Mock(return_value=self.session)
        self.connection.get_token_name = Mock(return_value="Offline token")
        stack = self.enterContext(ExitStack())
        self.site_update = stack.enter_context(
            patch(
                "mist_connection.mistapi.api.v1.sites.guests.updateSiteGuestAuthorization"
            )
        )
        self.org_update = stack.enter_context(
            patch(
                "mist_connection.mistapi.api.v1.orgs.guests.updateOrgGuestAuthorization"
            )
        )
        stack.enter_context(
            patch("mist_connection.time.time", return_value=1_700_000_000)
        )

    def test_only_provided_fields_are_sent_and_token_field_is_server_owned(self):
        result = self.connection.update_guest(
            "site-1",
            "wlan-1",
            "AA-BB-CC-DD-EE-FF",
            name="",
            email="guest@example.com",
            company="Example",
            field1="one",
            field2="two",
            field3="sponsor@example.com",
            field4="untrusted",
            minutes=60,
        )
        self.site_update.assert_called_once_with(
            self.session,
            "site-1",
            "aa:bb:cc:dd:ee:ff",
            body={
                "name": "",
                "email": "guest@example.com",
                "company": "Example",
                "field1": "one",
                "field2": "two",
                "field3": "sponsor@example.com",
                "field4": "Offline token",
                "minutes": 60,
            },
        )
        self.org_update.assert_not_called()
        self.assertEqual(
            result,
            {
                "success": True,
                "guest": {
                    "mac": "aa:bb:cc:dd:ee:ff",
                    "name": "",
                    "email": "guest@example.com",
                    "company": "Example",
                    "authorized_time": 1_700_000_000,
                    "authorized_expiring_time": 1_700_003_600,
                    "remaining_minutes": 60,
                    "is_expired": False,
                    "wlan_id": "wlan-1",
                },
            },
        )

    def test_omitted_fields_only_refresh_token_and_keep_existing_response_default(self):
        result = self.connection.update_guest("site-1", "wlan-1", "aabbccddeeff")
        self.assertEqual(
            self.site_update.call_args.kwargs["body"], {"field4": "Offline token"}
        )
        self.assertEqual(result["guest"]["remaining_minutes"], 1440)

    def test_zero_minutes_payload_preserves_existing_response_default(self):
        result = self.connection.update_guest(
            "site-1", "wlan-1", "aabbccddeeff", minutes=0
        )
        self.assertEqual(self.site_update.call_args.kwargs["body"]["minutes"], 0)
        self.assertEqual(result["guest"]["remaining_minutes"], 1440)

    def test_org_fallback_uses_identical_payload_and_result(self):
        expected = self.connection.update_guest(
            "site-1", "wlan-1", "aabbccddeeff", minutes=30
        )
        self.site_update.reset_mock()
        self.site_update.side_effect = RuntimeError("offline site failure")
        with self.assertLogs("mist_connection", level="WARNING"):
            actual = self.connection.update_guest(
                "site-1", "wlan-1", "aabbccddeeff", minutes=30
            )
        self.assertEqual(actual, expected)
        self.org_update.assert_called_once_with(
            self.session,
            "org-1",
            "aa:bb:cc:dd:ee:ff",
            body=self.site_update.call_args.kwargs["body"],
        )

    def test_both_update_failures_report_org_error(self):
        self.site_update.side_effect = RuntimeError("offline site failure")
        self.org_update.side_effect = RuntimeError("offline org failure")
        with self.assertLogs("mist_connection", level="ERROR"):
            result = self.connection.update_guest("site-1", "wlan-1", "aabbccddeeff")
        self.assertEqual(result, {"success": False, "error": UPDATE_FAILED_MESSAGE})
        self.assertNotIn("offline org failure", result["error"])

    def test_invalid_mac_and_session_failure_do_not_update(self):
        result = self.connection.update_guest("site-1", "wlan-1", "invalid")
        self.assertFalse(result["success"])
        self.assertIn("Invalid MAC address", result["error"])
        self.connection._get_session.side_effect = RuntimeError(
            "offline session failure"
        )
        result = self.connection.update_guest("site-1", "wlan-1", "aabbccddeeff")
        self.assertEqual(result, {"success": False, "error": UPDATE_FAILED_MESSAGE})
        self.site_update.assert_not_called()
        self.org_update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
