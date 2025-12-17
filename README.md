# MistGuestAuthorizations

Juniper Mist Guest WiFi Pre-Authorization Portal - A web application for setting up guest WiFi pre-authorizations for devices that don't support interactive captive portals.

## Overview

This application provides a web-based interface to manage guest WiFi pre-authorizations for the Juniper Mist wireless platform. It's designed for:

- **IoT devices** that cannot interact with captive portals
- **Printers, scanners, and other headless devices** 
- **Legacy equipment** without modern browser capabilities
- **Conference room displays and digital signage**
- **Medical devices and specialized equipment**

By pre-authorizing device MAC addresses, these devices can connect to guest WiFi networks without needing to complete captive portal authentication.

## Features

- 🌐 **Web-based Portal** - Modern, responsive UI for easy management
- 🔐 **Mist API Integration** - Direct integration with Juniper Mist Cloud
- 📍 **Site & WLAN Selection** - Browse and select sites and guest WLANs
- ➕ **Add Guest Authorizations** - Pre-authorize devices by MAC address
- 🔍 **Search Connected Clients** - Find and authorize already-connected devices
- ✏️ **Edit Authorizations** - Modify guest details and extend access
- 🗑️ **Revoke Access** - Remove device authorizations
- 📊 **Stats Dashboard** - View active, expiring, and expired authorizations
- ⏱️ **Flexible Duration** - Set authorization from 1 hour to 5 years
- 🐳 **Docker Ready** - Easy deployment with Docker/Podman

## Quick Start

### Prerequisites

- Python 3.9+
- Juniper Mist API Token with appropriate permissions
- (Optional) Docker or Podman for containerized deployment

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/jmorrison-juniper/MistGuestAuthorizations.git
   cd MistGuestAuthorizations
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Mist API credentials
   ```

5. **Run the application**
   ```bash
   python app.py
   ```

6. **Access the portal**
   Open http://localhost:5000 in your browser

### Docker Deployment

#### Option 1: Pull from GitHub Container Registry (Recommended)

```bash
# Configure environment
cp .env.example .env
# Edit .env with your Mist API credentials

# Pull and run
docker compose up -d
```

The container image is available at:
```
ghcr.io/jmorrison-juniper/mistguestauthorizations:latest
```

#### Option 2: Build Locally

```bash
# Configure environment
cp .env.example .env
# Edit .env with your Mist API credentials

# Build and run locally
docker compose -f docker-compose.dev.yml up -d
```

**Access the portal**: Open http://localhost:5000 in your browser

#### Podman Alternative

```bash
podman-compose up -d
# or
podman run -d -p 5000:5000 --env-file .env ghcr.io/jmorrison-juniper/mistguestauthorizations:latest
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MIST_APITOKEN` | Yes | - | Your Mist API token |
| `MIST_ORG_ID` | No | Auto-detect | Organization ID |
| `MIST_HOST` | No | `api.mist.com` | Mist API host |
| `PORT` | No | `5000` | Web server port |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `SECRET_KEY` | No | Auto-generated | Flask secret key |
| `TZ` | No | `UTC` | Timezone |

### Mist API Hosts

| Region | Host |
|--------|------|
| Global | `api.mist.com` |
| EU | `api.eu.mist.com` |
| GovCloud | `api.gc1.mist.com` |

### Required API Permissions

Your Mist API token needs the following permissions:
- **Read** access to Organization and Sites
- **Read/Write** access to WLANs
- **Read/Write** access to Guest Authorizations

## Usage

### Adding a Guest Authorization

1. Connect to the Mist API (automatic on page load)
2. Select a site from the dropdown
3. Select a guest WLAN
4. Click "Add Guest Authorization"
5. Enter the device MAC address and optional guest details
6. Set the authorization duration
7. Click "Authorize Guest"

### Finding Connected Clients

When adding a guest authorization, you can search for already-connected clients:

1. In the "Add Guest Authorization" dialog, use the "Search Connected Clients" panel
2. Search by MAC address, hostname, or IP
3. Click on a client to auto-populate the MAC address

### Managing Authorizations

- Click on any guest card to edit or revoke access
- Use the search box to filter the guest list
- Stats cards show total, active, expiring, and expired counts

## Architecture

```
MistGuestAuthorizations/
├── app.py                 # Flask application entry point
├── mist_connection.py     # Mist API connection module
├── templates/
│   └── index.html         # Main web UI
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container build file
├── docker-compose.yml     # Docker compose configuration
├── .env.example           # Environment template
├── .gitignore             # Git ignore rules
└── README.md              # This file
```

## Mist API Endpoints Used

This application uses the following Juniper Mist API endpoints via the `mistapi` Python SDK:

| API Endpoint | Method | Description |
|--------------|--------|-------------|
| `mistapi.api.v1.self.self.getSelf` | GET | Get current API token info and name |
| `mistapi.api.v1.orgs.orgs.getOrg` | GET | Get organization details |
| `mistapi.api.v1.orgs.sites.listOrgSites` | GET | List all sites in organization |
| `mistapi.api.v1.orgs.wlans.listOrgWlans` | GET | List organization-level WLANs |
| `mistapi.api.v1.orgs.templates.getOrgTemplate` | GET | Get WLAN template details |
| `mistapi.api.v1.orgs.sitegroups.getOrgSiteGroup` | GET | Get site group details |
| `mistapi.api.v1.sites.wlans.listSiteWlans` | GET | List site-level WLANs |
| `mistapi.api.v1.sites.guests.listSiteAllGuestAuthorizations` | GET | List all guest authorizations for a site |
| `mistapi.api.v1.orgs.guests.listOrgGuestAuthorizations` | GET | List org-level guest authorizations |
| `mistapi.api.v1.sites.guests.updateSiteGuestAuthorization` | PUT | Create/update guest authorization |
| `mistapi.api.v1.orgs.guests.updateOrgGuestAuthorization` | PUT | Create/update org-level guest authorization |
| `mistapi.api.v1.sites.stats.listSiteWirelessClientsStats` | GET | Search connected wireless clients |

> **Note**: Guest revocation uses PUT with `minutes=0` to immediately expire the authorization (the DELETE endpoint returns 200 but doesn't actually remove the guest).

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/test-connection` | Test Mist API connection |
| GET | `/api/sites` | List all sites |
| GET | `/api/sites/<site_id>/wlans` | List guest WLANs for a site |
| GET | `/api/sites/<site_id>/wlans/<wlan_id>/guests` | List authorized guests |
| POST | `/api/sites/<site_id>/wlans/<wlan_id>/guests` | Authorize a new guest |
| PUT | `/api/sites/<site_id>/wlans/<wlan_id>/guests/<mac>` | Update guest authorization |
| DELETE | `/api/sites/<site_id>/wlans/<wlan_id>/guests/<mac>` | Revoke guest access |
| GET | `/api/sites/<site_id>/clients/search` | Search connected clients |
| GET | `/health` | Health check endpoint |

## Troubleshooting

### Connection Issues

1. Verify your API token is correct and has not expired
2. Check the `MIST_HOST` matches your Mist cloud region
3. Ensure network connectivity to the Mist API

### No WLANs Showing

- WLANs must have guest portal features enabled or be open/PSK type
- Organization-level WLANs are also included

### Authorization Not Working

- Ensure the WLAN supports guest authorization
- Verify MAC address format is correct
- Check API token has write permissions

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## License

This project is licensed under the **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0)**.

See the [LICENSE](LICENSE) file for full details.

## Author

Joseph Morrison <jmorrison@juniper.net>

## Related Projects

- [MistSiteDashboard](https://github.com/jmorrison-juniper/MistSiteDashboard) - Mist Site Health Dashboard
- [MistHelper](https://github.com/jmorrison-juniper/MistHelper) - Mist API Helper Tools
