# Coolify &mdash; Deployment & Container Management Guide

[Coolify](https://coolify.io) is an open-source, self-hosted platform-as-a-service (PaaS) that manages Docker containers, automated builds from GitHub, environment variables, volumes, and health checks through a clean web dashboard.

---

## 1. Installing Coolify on the Oracle VM

Connect to your Oracle Cloud Ubuntu VM via SSH:

```bash
# 1. Run official Coolify installation script
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

The script installs Docker, Docker Compose, and launches Coolify's management containers.
Once complete, Coolify will output:
```text
Coolify is installed and running!
Access it via: http://<your-server-ip>:8000
```

> [!TIP]
> Because your VM is connected to Tailscale, you can access Coolify via its private Tailscale IP or MagicDNS without opening port 8000 on the Oracle public IP.

---

## 2. Deploying Relay via Coolify

### Step 2.1: Open Coolify Dashboard
1. Open your browser and navigate to your Coolify instance (e.g. `http://relay:8000` via Tailscale).
2. Follow the on-screen prompt to create your initial administrator account.

### Step 2.2: Add a New Resource
1. Click **Projects** &rarr; **Default Project** &rarr; **Production**.
2. Click **+ Add Resource** &rarr; **Public Repository**.
3. Fill in the repository details:
   - **Repository URL**: `https://github.com/q28i/relay`
   - **Branch**: `cloud`
   - **Build Pack**: **Docker Compose**

### Step 2.3: Configure Docker Compose in Coolify
In the application configuration screen:
1. Set **Docker Compose Location** to:
   `compose.coolify.yml`
2. Coolify will read the services and volumes automatically.

### Step 2.4: Configure Environment Variables
Under the **Environment Variables** tab in Coolify, add:

```ini
RELAY_ENABLE_AUTH=1
RELAY_HEADLESS=1
RELAY_USER_DATA_DIR=/data
RELAY_AUTH_KEY=your-secure-random-passphrase
ALLOWED_TAILSCALE_USERS=your-google-account@gmail.com
TZ=UTC
```

### Step 2.5: Verify Volume Mapping
Under **Storages / Volumes**, verify that the volume:
- `relay_data` is mounted to `/data` in the container.

This guarantees your SQLite database, uploaded media assets, and WhatsApp Web authentication tokens persist permanently across redeploys.

### Step 2.6: Deploy
1. Click **Deploy**.
2. Coolify will clone `q28i/relay` (branch `cloud`), build `Dockerfile.cloud` on the Ampere A1 ARM64 processor, and launch the container bound to `127.0.0.1:8000`.
3. Check the build logs: Coolify will show Python dependencies and Chromium installing cleanly.
4. When the healthcheck passes, the container status turns **Healthy**.

---

## 3. Alternative: Running Directly via Docker Compose (Without Coolify UI)

If you prefer deploying directly from the command line without the Coolify UI:

```bash
# 1. Clone repository on the server
git clone -b cloud https://github.com/q28i/relay.git /opt/relay
cd /opt/relay

# 2. Copy and customize environment variables
cp .env.cloud.example .env
nano .env

# 3. Build and launch with Docker Compose
docker compose -f compose.coolify.yml up -d --build

# 4. Check status and logs
docker compose -f compose.coolify.yml ps
docker compose -f compose.coolify.yml logs -f
```
