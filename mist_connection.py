#!/usr/bin/env python3
"""
Mist API Connection Module for MistGuestAuthorizations
Handles authentication and API calls to Juniper Mist Cloud for guest authorization.

Author: Joseph Morrison <jmorrison@juniper.net>
"""

import os
import re
import time
import logging
from typing import Dict, List, Optional, Any

import mistapi

logger = logging.getLogger(__name__)


def normalize_mac(mac: str) -> str:
    """Normalize a MAC address to lowercase with colons.
    
    Accepts formats like:
    - AA:BB:CC:DD:EE:FF
    - AA-BB-CC-DD-EE-FF
    - AABBCCDDEEFF
    - aabbccddeeff
    
    Returns: aa:bb:cc:dd:ee:ff
    """
    # Remove any separators and convert to lowercase
    mac_clean = re.sub(r'[:\-\.]', '', mac.lower())
    
    # Validate length
    if len(mac_clean) != 12:
        raise ValueError(f"Invalid MAC address: {mac}")
    
    # Validate hex characters
    if not re.match(r'^[0-9a-f]{12}$', mac_clean):
        raise ValueError(f"Invalid MAC address format: {mac}")
    
    # Insert colons
    return ':'.join(mac_clean[i:i+2] for i in range(0, 12, 2))


def mac_to_api_format(mac: str) -> str:
    """Convert MAC address to API format (12 hex chars, no separators).
    
    The Mist API DELETE endpoint expects MAC in format: ^[0-9a-fA-F]{12}$
    
    Returns: aabbccddeeff
    """
    # Remove any separators and convert to lowercase
    mac_clean = re.sub(r'[:\-\.]', '', mac.lower())
    
    # Validate length
    if len(mac_clean) != 12:
        raise ValueError(f"Invalid MAC address: {mac}")
    
    # Validate hex characters
    if not re.match(r'^[0-9a-f]{12}$', mac_clean):
        raise ValueError(f"Invalid MAC address format: {mac}")
    
    return mac_clean


class MistConnection:
    """Manages connection to the Juniper Mist Cloud API."""
    
    def __init__(self):
        """Initialize Mist API connection with credentials from environment."""
        self.api_token = os.getenv("MIST_APITOKEN")
        self.api_host = os.getenv("MIST_HOST", "api.mist.com")
        self.org_id = os.getenv("MIST_ORG_ID") or os.getenv("org_id")
        self.session = None
        
        if not self.api_token:
            logger.warning("MIST_APITOKEN not set in environment")
        
    def _get_session(self) -> mistapi.APISession:
        """Get or create an API session."""
        if self.session is None:
            self.session = mistapi.APISession(
                host=self.api_host,
                apitoken=self.api_token or ""
            )
        return self.session
    
    def get_token_name(self) -> str:
        """Get the human-readable name of the API token being used.
        
        Returns:
            The token name from the Mist API, or 'Unknown Token' if not available.
        """
        try:
            session = self._get_session()
            response = mistapi.api.v1.self.self.getSelf(session)
            self_data = response.data if hasattr(response, "data") else response
            if isinstance(self_data, dict):
                return self_data.get("name", "Unknown Token")
            return "Unknown Token"
        except Exception as error:
            logger.warning(f"Could not get token name: {error}")
            return "Unknown Token"
    
    def test_connection(self) -> Dict[str, Any]:
        """Test the API connection and return org info."""
        try:
            session = self._get_session()
            
            # Get org info to verify connection
            if self.org_id:
                response = mistapi.api.v1.orgs.orgs.getOrg(session, self.org_id)
                org_data = response.data if hasattr(response, "data") else response
                if isinstance(org_data, dict):
                    return {
                        "success": True,
                        "org_name": org_data.get("name", "Unknown"),
                        "org_id": self.org_id
                    }
                else:
                    return {"success": True, "org_name": "Unknown", "org_id": self.org_id}
            else:
                # List orgs to find the first available
                response = mistapi.api.v1.self.self.getSelf(session)
                self_data = response.data if hasattr(response, "data") else response
                privileges = self_data.get("privileges", []) if isinstance(self_data, dict) else []
                
                if privileges:
                    first_org = privileges[0]
                    self.org_id = first_org.get("org_id")
                    return {
                        "success": True,
                        "org_name": first_org.get("name", "Unknown"),
                        "org_id": self.org_id
                    }
                else:
                    return {"success": False, "error": "No organizations found for this API token"}
                    
        except Exception as error:
            logger.error(f"Connection test failed: {error}")
            return {"success": False, "error": str(error)}
    
    def get_sites(self, filter_guest_wlans: bool = True) -> List[Dict[str, Any]]:
        """Get all sites in the organization.
        
        Args:
            filter_guest_wlans: If True, only return sites that have at least one
                               WLAN with a guest captive portal enabled.
                               
        This is optimized to avoid per-site API calls by:
        1. Getting org-level WLANs with guest portal
        2. Looking up templates to find which sites/sitegroups they apply to
        3. Expanding sitegroups to get site IDs
        """
        try:
            session = self._get_session()
            
            if not self.org_id:
                test_result = self.test_connection()
                if not test_result["success"]:
                    raise ValueError("Could not determine organization ID")
            
            org_id: str = self.org_id or ""
            
            response = mistapi.api.v1.orgs.sites.listOrgSites(
                session, 
                org_id, 
                limit=1000
            )
            sites = mistapi.get_all(response=response, mist_session=session) or []
            
            # Sort sites by name
            sites.sort(key=lambda site: site.get("name", "").lower())
            
            # If not filtering, return all sites
            if not filter_guest_wlans:
                return [
                    {
                        "id": site.get("id"),
                        "name": site.get("name", "Unknown"),
                        "address": site.get("address", ""),
                        "country_code": site.get("country_code", ""),
                        "timezone": site.get("timezone", "")
                    }
                    for site in sites
                ]
            
            # Build set of site IDs that have guest WLANs
            # We only query org WLANs + templates + sitegroups (no per-site queries)
            sites_with_guest_wlans: set = set()
            all_site_ids = {site.get("id") for site in sites}
            
            try:
                # Get org-level WLANs
                response = mistapi.api.v1.orgs.wlans.listOrgWlans(
                    session,
                    org_id,
                    limit=1000
                )
                org_wlans = mistapi.get_all(response=response, mist_session=session) or []
                
                # Cache for templates and sitegroups to avoid duplicate lookups
                template_cache: Dict[str, Any] = {}
                sitegroup_cache: Dict[str, List[str]] = {}
                
                for wlan in org_wlans:
                    portal = wlan.get("portal", {})
                    if not (portal.get("enabled", False) and wlan.get("enabled", True)):
                        continue
                    
                    # This is a guest WLAN - find which sites it applies to
                    template_id = wlan.get("template_id")
                    
                    if template_id:
                        # WLAN is part of a template - get template's site/sitegroup assignments
                        if template_id not in template_cache:
                            try:
                                tmpl_response = mistapi.api.v1.orgs.templates.getOrgTemplate(
                                    session, org_id, template_id
                                )
                                template_cache[template_id] = tmpl_response.data if hasattr(tmpl_response, 'data') else {}
                            except Exception as e:
                                logger.debug(f"Could not fetch template {template_id}: {e}")
                                template_cache[template_id] = {}
                        
                        template = template_cache[template_id]
                        applies = template.get("applies", {})
                        
                        # Add directly assigned sites
                        for site_id in applies.get("site_ids", []) or []:
                            sites_with_guest_wlans.add(site_id)
                        
                        # Get sites from sitegroups
                        for sitegroup_id in applies.get("sitegroup_ids", []) or []:
                            if sitegroup_id not in sitegroup_cache:
                                try:
                                    sg_response = mistapi.api.v1.orgs.sitegroups.getOrgSiteGroup(
                                        session, org_id, sitegroup_id
                                    )
                                    sitegroup = sg_response.data if hasattr(sg_response, 'data') else {}
                                    sitegroup_cache[sitegroup_id] = sitegroup.get("site_ids", []) or []
                                except Exception as e:
                                    logger.debug(f"Could not fetch sitegroup {sitegroup_id}: {e}")
                                    sitegroup_cache[sitegroup_id] = []
                            
                            for site_id in sitegroup_cache[sitegroup_id]:
                                sites_with_guest_wlans.add(site_id)
                    else:
                        # WLAN not in template - check apply_to and site_ids/sitegroup_ids
                        apply_to = wlan.get("apply_to", "")
                        if apply_to == "all":
                            # Applies to all sites - add all and we're done
                            sites_with_guest_wlans.update(all_site_ids)
                        else:
                            # Check direct site assignments
                            for site_id in wlan.get("site_ids", []) or []:
                                sites_with_guest_wlans.add(site_id)
                            # Check sitegroup assignments
                            for sitegroup_id in wlan.get("sitegroup_ids", []) or []:
                                if sitegroup_id not in sitegroup_cache:
                                    try:
                                        sg_response = mistapi.api.v1.orgs.sitegroups.getOrgSiteGroup(
                                            session, org_id, sitegroup_id
                                        )
                                        sitegroup = sg_response.data if hasattr(sg_response, 'data') else {}
                                        sitegroup_cache[sitegroup_id] = sitegroup.get("site_ids", []) or []
                                    except Exception as e:
                                        logger.debug(f"Could not fetch sitegroup {sitegroup_id}: {e}")
                                        sitegroup_cache[sitegroup_id] = []
                                
                                for site_id in sitegroup_cache[sitegroup_id]:
                                    sites_with_guest_wlans.add(site_id)
                                    
            except Exception as e:
                logger.warning(f"Could not fetch org WLANs for filtering: {e}")
            
            # Build result list - only sites with guest WLANs
            result_sites = [
                {
                    "id": site.get("id"),
                    "name": site.get("name", "Unknown"),
                    "address": site.get("address", ""),
                    "country_code": site.get("country_code", ""),
                    "timezone": site.get("timezone", "")
                }
                for site in sites
                if site.get("id") in sites_with_guest_wlans
            ]
            
            logger.info(f"Found {len(result_sites)} sites with guest WLANs (out of {len(sites)} total)")
            return result_sites
            
        except Exception as error:
            logger.error(f"Error fetching sites: {error}")
            raise

    def get_guest_wlans(self, site_id: str) -> List[Dict[str, Any]]:
        """Get WLANs with guest portal enabled for a site."""
        try:
            session = self._get_session()
            org_id: str = self.org_id or ""
            
            # Get site WLANs
            site_wlans = []
            try:
                response = mistapi.api.v1.sites.wlans.listSiteWlans(
                    session,
                    site_id,
                    limit=1000
                )
                site_wlans = mistapi.get_all(response=response, mist_session=session) or []
            except Exception as e:
                logger.debug(f"Could not fetch site WLANs: {e}")
            
            # Get org WLANs (they may apply to this site)
            org_wlans = []
            try:
                response = mistapi.api.v1.orgs.wlans.listOrgWlans(
                    session,
                    org_id,
                    limit=1000
                )
                org_wlans = mistapi.get_all(response=response, mist_session=session) or []
            except Exception as e:
                logger.debug(f"Could not fetch org WLANs: {e}")
            
            # Combine and filter for guest-portal enabled WLANs
            all_wlans = site_wlans + org_wlans
            guest_wlans = []
            seen_ids = set()
            
            for wlan in all_wlans:
                wlan_id = wlan.get("id")
                if wlan_id in seen_ids:
                    continue
                seen_ids.add(wlan_id)
                
                # Check if WLAN is enabled and has guest portal features
                if not wlan.get("enabled", True):
                    continue
                
                # Get portal and auth settings
                portal = wlan.get("portal", {})
                auth = wlan.get("auth", {})
                auth_type = auth.get("type", "")
                
                # A WLAN is a guest WLAN if it has portal enabled
                # Portal enabled means the WLAN is configured for guest access
                # This is the primary indicator for guest pre-authorization capability
                portal_enabled = portal.get("enabled", False)
                
                # Only include WLANs with portal enabled (actual guest WLANs)
                if portal_enabled:
                    guest_wlans.append({
                        "id": wlan_id,
                        "ssid": wlan.get("ssid", "Unknown"),
                        "enabled": wlan.get("enabled", True),
                        "auth_type": auth_type,
                        "portal_enabled": portal.get("enabled", False),
                        "portal_auth": portal.get("auth", "none"),
                        "org_level": wlan in org_wlans
                    })
            
            # Sort by SSID name
            guest_wlans.sort(key=lambda w: w.get("ssid", "").lower())
            
            return guest_wlans
            
        except Exception as error:
            logger.error(f"Error fetching guest WLANs for site {site_id}: {error}")
            raise

    def get_wlan_guests(self, site_id: str, wlan_id: str) -> List[Dict[str, Any]]:
        """Get list of authorized guests for a WLAN."""
        try:
            session = self._get_session()
            
            # Try to get guests from the site WLAN
            try:
                response = mistapi.api.v1.sites.guests.listSiteAllGuestAuthorizations(
                    session,
                    site_id,
                    wlan_id=wlan_id
                )
                guests_data = response.data if hasattr(response, "data") else response
                
                if isinstance(guests_data, list):
                    guests = guests_data
                elif isinstance(guests_data, dict):
                    guests = guests_data.get("results", [])
                else:
                    guests = []
                    
            except Exception as e:
                logger.debug(f"Could not fetch guests from site endpoint: {e}")
                # Try org-level endpoint
                try:
                    org_id: str = self.org_id or ""
                    response = mistapi.api.v1.orgs.guests.listOrgGuestAuthorizations(
                        session,
                        org_id
                    )
                    guests_data = response.data if hasattr(response, "data") else response
                    
                    if isinstance(guests_data, list):
                        guests = guests_data
                    elif isinstance(guests_data, dict):
                        guests = guests_data.get("results", [])
                    else:
                        guests = []
                except Exception as e2:
                    logger.debug(f"Could not fetch guests from org endpoint: {e2}")
                    guests = []
            
            # Format guest data
            formatted_guests = []
            current_time = int(time.time())
            
            for guest in guests:
                mac = guest.get("mac", "")
                authorized_time = guest.get("authorized_time", 0)
                authorized_expiring_time = guest.get("authorized_expiring_time", 0)
                
                # Calculate remaining time
                remaining_minutes = 0
                is_expired = True
                if authorized_expiring_time > current_time:
                    remaining_minutes = (authorized_expiring_time - current_time) // 60
                    is_expired = False
                
                formatted_guests.append({
                    "mac": mac,
                    "name": guest.get("name", ""),
                    "email": guest.get("email", ""),
                    "company": guest.get("company", ""),
                    "field1": guest.get("field1", ""),
                    "field2": guest.get("field2", ""),
                    "field3": guest.get("field3", ""),
                    "field4": guest.get("field4", ""),
                    "authorized_time": authorized_time,
                    "authorized_expiring_time": authorized_expiring_time,
                    "remaining_minutes": remaining_minutes,
                    "is_expired": is_expired,
                    "auth_method": guest.get("auth_method", "manual"),
                    "ssid": guest.get("ssid", ""),
                    "wlan_id": guest.get("wlan_id", wlan_id)
                })
            
            # Sort by expiring time (active first, then expired)
            formatted_guests.sort(key=lambda g: (g["is_expired"], -g["authorized_expiring_time"]))
            
            return formatted_guests
            
        except Exception as error:
            logger.error(f"Error fetching guests for WLAN {wlan_id}: {error}")
            raise

    def authorize_guest(
        self,
        site_id: str,
        wlan_id: str,
        mac: str,
        name: str = "",
        email: str = "",
        company: str = "",
        field1: str = "",
        field2: str = "",
        field3: str = "",
        field4: str = "",
        minutes: int = 1440,
        notify: bool = False
    ) -> Dict[str, Any]:
        """Authorize a guest device on a WLAN.
        
        Args:
            site_id: Site ID
            wlan_id: WLAN ID
            mac: Device MAC address
            name: Guest name (optional)
            email: Guest email (optional)
            company: Guest company (optional)
            field1: Custom field 1 (optional)
            field2: Custom field 2 (optional)
            field3: Custom field 3 (optional)
            field4: Custom field 4 (optional)
            minutes: Authorization duration in minutes (default: 1440 = 24 hours)
            notify: Whether to send notification (optional)
        
        Returns:
            Dict with success status and guest info or error
        """
        try:
            session = self._get_session()
            
            # Normalize MAC address
            try:
                normalized_mac = normalize_mac(mac)
            except ValueError as e:
                return {"success": False, "error": str(e)}
            
            # Build the guest authorization payload
            guest_data = {
                "mac": normalized_mac,
                "minutes": minutes,
                "authorized": True
            }
            
            if name:
                guest_data["name"] = name
            if email:
                guest_data["email"] = email
            if company:
                guest_data["company"] = company
            if field1:
                guest_data["field1"] = field1
            if field2:
                guest_data["field2"] = field2
            if field3:
                guest_data["field3"] = field3
            
            # field4 is always auto-populated with the API token name
            token_name = self.get_token_name()
            guest_data["field4"] = token_name
            
            if notify:
                guest_data["notify"] = notify
            
            # Add wlan_id to the payload for authorization
            guest_data["wlan_id"] = wlan_id
            
            # Use updateSiteGuestAuthorization to create/update guest authorization
            # The Mist API uses the same endpoint for both create and update
            try:
                response = mistapi.api.v1.sites.guests.updateSiteGuestAuthorization(
                    session,
                    site_id,
                    normalized_mac,
                    body=guest_data
                )
                result = response.data if hasattr(response, "data") else response
                
                # Calculate times
                current_time = int(time.time())
                authorized_expiring_time = current_time + (minutes * 60)
                
                return {
                    "success": True,
                    "guest": {
                        "mac": normalized_mac,
                        "name": name,
                        "email": email,
                        "company": company,
                        "authorized_time": current_time,
                        "authorized_expiring_time": authorized_expiring_time,
                        "remaining_minutes": minutes,
                        "is_expired": False,
                        "wlan_id": wlan_id
                    }
                }
                
            except Exception as e:
                logger.warning(f"Site-level authorization failed: {e}")
                # Try org-level if site-level fails
                try:
                    org_id: str = self.org_id or ""
                    
                    response = mistapi.api.v1.orgs.guests.updateOrgGuestAuthorization(
                        session,
                        org_id,
                        normalized_mac,
                        body=guest_data
                    )
                    result = response.data if hasattr(response, "data") else response
                    
                    current_time = int(time.time())
                    authorized_expiring_time = current_time + (minutes * 60)
                    
                    return {
                        "success": True,
                        "guest": {
                            "mac": normalized_mac,
                            "name": name,
                            "email": email,
                            "company": company,
                            "authorized_time": current_time,
                            "authorized_expiring_time": authorized_expiring_time,
                            "remaining_minutes": minutes,
                            "is_expired": False,
                            "wlan_id": wlan_id
                        }
                    }
                except Exception as e2:
                    logger.error(f"Org-level authorization also failed: {e2}")
                    return {"success": False, "error": f"Authorization failed: {str(e2)}"}
                    
        except Exception as error:
            logger.error(f"Error authorizing guest {mac}: {error}")
            return {"success": False, "error": str(error)}

    def deauthorize_guest(self, site_id: str, wlan_id: str, mac: str) -> Dict[str, Any]:
        """Remove guest authorization from a WLAN.
        
        Instead of using DELETE (which doesn't work reliably for org-level WLANs),
        we set minutes=0 which immediately expires the guest authorization.
        
        Args:
            site_id: Site ID
            wlan_id: WLAN ID
            mac: Device MAC address
        
        Returns:
            Dict with success status or error
        """
        try:
            session = self._get_session()
            
            # Normalize MAC to format with colons (aa:bb:cc:dd:ee:ff)
            try:
                normalized_mac = normalize_mac(mac)
            except ValueError as e:
                return {"success": False, "error": str(e)}
            
            logger.info(f"Attempting to deauthorize guest MAC: {normalized_mac} by setting minutes=0")
            
            # Use updateSiteGuestAuthorization with minutes=0 to expire the authorization
            # This works more reliably than DELETE for org-level WLANs
            response = mistapi.api.v1.sites.guests.updateSiteGuestAuthorization(
                session,
                site_id,
                normalized_mac,
                body={"minutes": 0}
            )
            
            # Check the response status code
            status_code = getattr(response, 'status_code', None)
            logger.info(f"Deauthorize response status code: {status_code}")
            
            if status_code is not None and status_code >= 200 and status_code < 300:
                return {"success": True}
            else:
                error_data = getattr(response, 'data', {})
                error_msg = error_data.get('detail', f"API error (status: {status_code})")
                return {"success": False, "error": error_msg}
                    
        except Exception as error:
            logger.error(f"Error deauthorizing guest {mac}: {error}")
            return {"success": False, "error": str(error)}

    def update_guest(
        self,
        site_id: str,
        wlan_id: str,
        mac: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        company: Optional[str] = None,
        field1: Optional[str] = None,
        field2: Optional[str] = None,
        field3: Optional[str] = None,
        field4: Optional[str] = None,
        minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """Update an existing guest authorization.
        
        Args:
            site_id: Site ID
            wlan_id: WLAN ID
            mac: Device MAC address
            name: New guest name (optional)
            email: New guest email (optional)
            company: New guest company (optional)
            field1: Custom field 1 (optional)
            field2: Custom field 2 (optional)
            field3: Custom field 3 - Sponsor Email (optional)
            field4: Custom field 4 - Auto-populated with token name (ignored)
            minutes: New authorization duration in minutes (optional)
        
        Returns:
            Dict with success status and updated guest info or error
        """
        try:
            session = self._get_session()
            
            # Normalize MAC address
            try:
                normalized_mac = normalize_mac(mac)
            except ValueError as e:
                return {"success": False, "error": str(e)}
            
            # Build update payload with only provided fields
            update_data = {}
            if name is not None:
                update_data["name"] = name
            if email is not None:
                update_data["email"] = email
            if company is not None:
                update_data["company"] = company
            if field1 is not None:
                update_data["field1"] = field1
            if field2 is not None:
                update_data["field2"] = field2
            if field3 is not None:
                update_data["field3"] = field3
            
            # field4 is always auto-populated with the API token name (regardless of passed value)
            token_name = self.get_token_name()
            update_data["field4"] = token_name
            
            if minutes is not None:
                update_data["minutes"] = minutes
            
            if not update_data:
                return {"success": False, "error": "No fields to update"}
            
            # Try site-level update first
            try:
                response = mistapi.api.v1.sites.guests.updateSiteGuestAuthorization(
                    session,
                    site_id,
                    normalized_mac,
                    body=update_data
                )
                result = response.data if hasattr(response, "data") else response
                
                current_time = int(time.time())
                authorized_expiring_time = current_time + ((minutes or 1440) * 60)
                
                return {
                    "success": True,
                    "guest": {
                        "mac": normalized_mac,
                        "name": name or "",
                        "email": email or "",
                        "company": company or "",
                        "authorized_time": current_time,
                        "authorized_expiring_time": authorized_expiring_time,
                        "remaining_minutes": minutes or 1440,
                        "is_expired": False,
                        "wlan_id": wlan_id
                    }
                }
                
            except Exception as e:
                logger.warning(f"Site-level update failed: {e}")
                # Try org-level if site-level fails
                try:
                    org_id: str = self.org_id or ""
                    response = mistapi.api.v1.orgs.guests.updateOrgGuestAuthorization(
                        session,
                        org_id,
                        normalized_mac,
                        body=update_data
                    )
                    result = response.data if hasattr(response, "data") else response
                    
                    current_time = int(time.time())
                    authorized_expiring_time = current_time + ((minutes or 1440) * 60)
                    
                    return {
                        "success": True,
                        "guest": {
                            "mac": normalized_mac,
                            "name": name or "",
                            "email": email or "",
                            "company": company or "",
                            "authorized_time": current_time,
                            "authorized_expiring_time": authorized_expiring_time,
                            "remaining_minutes": minutes or 1440,
                            "is_expired": False,
                            "wlan_id": wlan_id
                        }
                    }
                except Exception as e2:
                    logger.error(f"Org-level update also failed: {e2}")
                    return {"success": False, "error": f"Update failed: {str(e2)}"}
                    
        except Exception as error:
            logger.error(f"Error updating guest {mac}: {error}")
            return {"success": False, "error": str(error)}

    def search_wireless_clients(self, site_id: str, query: str = "") -> List[Dict[str, Any]]:
        """Search for wireless clients connected to a site.
        
        Args:
            site_id: Site ID to search
            query: Optional search query (MAC, hostname, IP)
        
        Returns:
            List of client info dictionaries
        """
        try:
            session = self._get_session()
            
            # Get connected wireless clients
            try:
                response = mistapi.api.v1.sites.stats.listSiteWirelessClientsStats(
                    session,
                    site_id,
                    limit=1000
                )
                clients_data = mistapi.get_all(response=response, mist_session=session) or []
            except Exception as e:
                logger.debug(f"Could not fetch wireless client stats: {e}")
                clients_data = []
            
            # Format and filter clients
            clients = []
            query_lower = query.lower() if query else ""
            
            for client in clients_data:
                mac = client.get("mac", "")
                hostname = client.get("hostname", "")
                ip = client.get("ip", "")
                ssid = client.get("ssid", "")
                
                # Filter by query if provided
                if query_lower:
                    searchable = f"{mac} {hostname} {ip} {ssid}".lower()
                    if query_lower not in searchable:
                        continue
                
                clients.append({
                    "mac": mac,
                    "hostname": hostname,
                    "ip": ip,
                    "ssid": ssid,
                    "ap_mac": client.get("ap_mac", ""),
                    "band": client.get("band", ""),
                    "rssi": client.get("rssi", 0),
                    "os": client.get("os", ""),
                    "manufacture": client.get("manufacture", ""),
                    "is_connected": True
                })
            
            # Sort by hostname/MAC
            clients.sort(key=lambda c: (c.get("hostname") or c.get("mac", "")).lower())
            
            return clients
            
        except Exception as error:
            logger.error(f"Error searching wireless clients: {error}")
            raise
