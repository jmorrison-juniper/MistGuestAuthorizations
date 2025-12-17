#!/usr/bin/env python3
"""
MistGuestAuthorizations - Juniper Mist Guest WiFi Pre-Authorization Portal
A Flask-based web application for setting up guest WiFi pre-authorizations
for devices that don't support interactive captive portals.

Author: Joseph Morrison <jmorrison@juniper.net>
Version: 24.12.17.10.00
"""

from __future__ import annotations

import os
import sys
import io
import csv
import logging
from datetime import datetime
from functools import wraps
from typing import Optional

from flask import Flask, render_template, jsonify, request, Response
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Determine log handlers - only use file handler if logs directory exists and is writable
log_handlers = [logging.StreamHandler(sys.stdout)]
log_file_path = "/config/logs/app.log"
if os.path.exists("/config/logs") and os.access("/config/logs", os.W_OK):
    try:
        log_handlers.append(logging.FileHandler(log_file_path))
    except (PermissionError, IOError):
        pass  # Skip file logging if we can't write

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=log_handlers
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", os.urandom(24).hex())

# Import Mist connection module
from mist_connection import MistConnection

# Module-level Mist connection instance
_mist_connection: Optional[MistConnection] = None


def get_mist_connection() -> MistConnection:
    """Get or create a Mist API connection."""
    global _mist_connection
    if _mist_connection is None:
        _mist_connection = MistConnection()
    return _mist_connection


@app.route("/")
def index():
    """Render the main dashboard page."""
    return render_template("index.html")


@app.route("/api/test-connection", methods=["POST"])
def test_connection():
    """Test the Mist API connection."""
    try:
        mist = get_mist_connection()
        result = mist.test_connection()
        if result["success"]:
            logger.info("Mist API connection test successful")
            return jsonify({
                "success": True,
                "message": "Connected to Mist API successfully",
                "org_name": result.get("org_name", "Unknown")
            })
        else:
            logger.warning(f"Mist API connection test failed: {result.get('error', 'Unknown error')}")
            return jsonify({"success": False, "error": result.get("error", "Connection failed")}), 400
    except Exception as error:
        logger.error(f"Connection test error: {error}")
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/api/sites", methods=["GET"])
def get_sites():
    """Get list of sites that have at least one guest WLAN with captive portal."""
    try:
        mist = get_mist_connection()
        sites = mist.get_sites(filter_guest_wlans=True)
        logger.info(f"Retrieved {len(sites)} sites with guest WLANs from Mist API")
        return jsonify({"success": True, "sites": sites})
    except Exception as error:
        logger.error(f"Error fetching sites: {error}")
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/api/sites/<site_id>/wlans", methods=["GET"])
def get_site_wlans(site_id):
    """Get list of WLANs for a specific site (with guest portal enabled)."""
    try:
        mist = get_mist_connection()
        wlans = mist.get_guest_wlans(site_id)
        logger.info(f"Retrieved {len(wlans)} guest WLANs for site {site_id}")
        return jsonify({"success": True, "wlans": wlans})
    except Exception as error:
        logger.error(f"Error fetching WLANs for site {site_id}: {error}")
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/api/sites/<site_id>/wlans/<wlan_id>/guests", methods=["GET"])
def get_wlan_guests(site_id, wlan_id):
    """Get list of authorized guests for a specific WLAN."""
    try:
        mist = get_mist_connection()
        guests = mist.get_wlan_guests(site_id, wlan_id)
        logger.info(f"Retrieved {len(guests)} authorized guests for WLAN {wlan_id}")
        return jsonify({"success": True, "guests": guests})
    except Exception as error:
        logger.error(f"Error fetching guests for WLAN {wlan_id}: {error}")
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/api/sites/<site_id>/wlans/<wlan_id>/guests", methods=["POST"])
def authorize_guest(site_id, wlan_id):
    """Authorize a new guest for a specific WLAN."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        mac = data.get("mac")
        if not mac:
            return jsonify({"success": False, "error": "MAC address is required"}), 400
        
        mist = get_mist_connection()
        result = mist.authorize_guest(
            site_id=site_id,
            wlan_id=wlan_id,
            mac=mac,
            name=data.get("name", ""),
            email=data.get("email", ""),
            company=data.get("company", ""),
            field1=data.get("field1", ""),
            field2=data.get("field2", ""),
            field3=data.get("field3", ""),
            field4=data.get("field4", ""),
            minutes=data.get("minutes", 1440),
            notify=data.get("notify", False)
        )
        
        if result["success"]:
            logger.info(f"Successfully authorized guest {mac} on WLAN {wlan_id}")
            return jsonify({"success": True, "guest": result.get("guest", {})})
        else:
            logger.warning(f"Failed to authorize guest {mac}: {result.get('error')}")
            return jsonify({"success": False, "error": result.get("error")}), 400
            
    except Exception as error:
        logger.error(f"Error authorizing guest: {error}")
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/api/sites/<site_id>/wlans/<wlan_id>/guests/<path:guest_mac>", methods=["DELETE"])
def deauthorize_guest(site_id, wlan_id, guest_mac):
    """Deauthorize (remove) a guest from a specific WLAN."""
    try:
        mist = get_mist_connection()
        result = mist.deauthorize_guest(site_id, wlan_id, guest_mac)
        
        if result["success"]:
            logger.info(f"Successfully deauthorized guest {guest_mac} from WLAN {wlan_id}")
            return jsonify({"success": True})
        else:
            logger.warning(f"Failed to deauthorize guest {guest_mac}: {result.get('error')}")
            return jsonify({"success": False, "error": result.get("error")}), 400
            
    except Exception as error:
        logger.error(f"Error deauthorizing guest: {error}")
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/api/sites/<site_id>/wlans/<wlan_id>/guests/<path:guest_mac>", methods=["PUT"])
def update_guest(site_id, wlan_id, guest_mac):
    """Update an existing guest authorization."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        mist = get_mist_connection()
        result = mist.update_guest(
            site_id=site_id,
            wlan_id=wlan_id,
            mac=guest_mac,
            name=data.get("name"),
            email=data.get("email"),
            company=data.get("company"),
            field1=data.get("field1"),
            field2=data.get("field2"),
            field3=data.get("field3"),
            field4=data.get("field4"),
            minutes=data.get("minutes")
        )
        
        if result["success"]:
            logger.info(f"Successfully updated guest {guest_mac} on WLAN {wlan_id}")
            return jsonify({"success": True, "guest": result.get("guest", {})})
        else:
            logger.warning(f"Failed to update guest {guest_mac}: {result.get('error')}")
            return jsonify({"success": False, "error": result.get("error")}), 400
            
    except Exception as error:
        logger.error(f"Error updating guest: {error}")
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/api/sites/<site_id>/clients/search", methods=["GET"])
def search_clients(site_id):
    """Search for wireless clients connected to the site."""
    try:
        query = request.args.get("query", "")
        mist = get_mist_connection()
        clients = mist.search_wireless_clients(site_id, query)
        logger.info(f"Found {len(clients)} clients matching '{query}' at site {site_id}")
        return jsonify({"success": True, "clients": clients})
    except Exception as error:
        logger.error(f"Error searching clients: {error}")
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/api/csv-template", methods=["GET"])
def get_csv_template():
    """Generate and return an example CSV template for bulk guest import."""
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        headers = [
            "site_name",
            "ssid", 
            "mac",
            "name",
            "email",
            "company",
            "field1",
            "field2",
            "field3_sponsor_email",
            "minutes"
        ]
        writer.writerow(headers)
        
        # Write example row
        example_row = [
            "Main Office",
            "Guest-WiFi",
            "AA:BB:CC:DD:EE:FF",
            "John Smith",
            "john.smith@example.com",
            "Acme Corp",
            "Badge #12345",
            "Building A",
            "sponsor@company.com",
            "1440"
        ]
        writer.writerow(example_row)
        
        # Second example row
        example_row2 = [
            "Branch Office",
            "Visitor-Network",
            "11:22:33:44:55:66",
            "Jane Doe",
            "jane.doe@example.com",
            "Partner Inc",
            "",
            "",
            "host@company.com",
            "480"
        ]
        writer.writerow(example_row2)
        
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=guest_import_template.csv"}
        )
    except Exception as error:
        logger.error(f"Error generating CSV template: {error}")
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/api/sites-wlans-map", methods=["GET"])
def get_sites_wlans_map():
    """Get a mapping of site names to site IDs and WLAN SSIDs to WLAN IDs."""
    try:
        mist = get_mist_connection()
        sites = mist.get_sites()
        
        # Build mapping: {site_name: {id: site_id, wlans: {ssid: wlan_id}}}
        sites_map = {}
        for site in sites:
            site_name = site.get("name", "").lower().strip()
            site_id = site.get("id")
            if site_name and site_id:
                wlans = mist.get_guest_wlans(site_id)
                wlan_map = {}
                for wlan in wlans:
                    ssid = wlan.get("ssid", "").lower().strip()
                    wlan_id = wlan.get("id")
                    if ssid and wlan_id:
                        wlan_map[ssid] = wlan_id
                sites_map[site_name] = {
                    "id": site_id,
                    "wlans": wlan_map
                }
        
        logger.info(f"Built sites/WLANs map with {len(sites_map)} sites")
        return jsonify({"success": True, "map": sites_map})
    except Exception as error:
        logger.error(f"Error building sites/WLANs map: {error}")
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/api/bulk-import", methods=["POST"])
def bulk_import_guests():
    """Import a single guest from the bulk import (called per-row by frontend)."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400
        
        site_id = data.get("site_id")
        wlan_id = data.get("wlan_id")
        mac = data.get("mac")
        
        if not site_id:
            return jsonify({"success": False, "error": "Site not found"}), 400
        if not wlan_id:
            return jsonify({"success": False, "error": "WLAN not found"}), 400
        if not mac:
            return jsonify({"success": False, "error": "MAC address is required"}), 400
        
        mist = get_mist_connection()
        result = mist.authorize_guest(
            site_id=site_id,
            wlan_id=wlan_id,
            mac=mac,
            name=data.get("name", ""),
            email=data.get("email", ""),
            company=data.get("company", ""),
            field1=data.get("field1", ""),
            field2=data.get("field2", ""),
            field3=data.get("field3", ""),
            minutes=int(data.get("minutes", 1440))
        )
        
        if result["success"]:
            logger.info(f"Bulk import: Successfully authorized guest {mac}")
            return jsonify({"success": True, "guest": result.get("guest", {})})
        else:
            logger.warning(f"Bulk import: Failed to authorize guest {mac}: {result.get('error')}")
            return jsonify({"success": False, "error": result.get("error")}), 400
            
    except Exception as error:
        logger.error(f"Bulk import error: {error}")
        return jsonify({"success": False, "error": str(error)}), 500


@app.route("/health")
def health_check():
    """Health check endpoint for container orchestration."""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


if __name__ == "__main__":
    # Get port from environment or default to 5000
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    
    logger.info(f"Starting MistGuestAuthorizations on port {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
