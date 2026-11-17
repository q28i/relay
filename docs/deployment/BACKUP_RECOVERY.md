# Backup, Disaster Recovery & Volume Maintenance

This guide explains how to back up your persistent Relay database, user media, and WhatsApp Web session data, and how to perform a disaster recovery restore in under 2 minutes.

---

## 1. Directory Structure of Persistent Volume (`/data`)

All state is stored inside the container at `/data`, mapped to the host Docker volume `relay_data` (`/var/lib/docker/volumes/relay_data/_data` on Ubuntu):

```text
/data/
├── whatsapp_web.db                  # SQLite database (contacts, templates, campaigns, jobs, logs)
├── whatsapp_web.db-wal              # SQLite Write-Ahead Log
├── whatsapp_web.db-shm              # SQLite Shared Memory
├── config.json                      # User preferences, throttling rates, automation profile
├── device_identity.json             # Persistent installation identity
├── uploads/
│   └── media/                       # Uploaded campaign images and attachments
└── whatsapp_browser_session/        # Chromium User Data Directory
    ├── Default/
    │   ├── IndexedDB/               # WhatsApp Web crypto keys & indexed chats
    │   ├── Local Storage/           # WhatsApp Web session credentials
    │   └── ...
    └── ...
```

---

## 2. Automated Daily Backup via Cron

You can set up a lightweight, zero-downtime daily backup script on the Oracle VM:

### Create Backup Script
Create `/usr/local/bin/backup-relay.sh`:

```bash
sudo tee /usr/local/bin/backup-relay.sh > /dev/null << 'EOF'
#!/bin/bash
set -e

BACKUP_DIR="/opt/relay-backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DEST_FILE="${BACKUP_DIR}/relay_backup_${TIMESTAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"

# 1. Safely snapshot SQLite database using sqlite3 VACUUM INTO (WAL safe)
docker exec relay-dispatcher python3 -c '
import sqlite3
con = sqlite3.connect("/data/whatsapp_web.db")
con.execute("VACUUM INTO \"/data/whatsapp_web_backup.db\"")
con.close()
'

# 2. Archive SQLite snapshot, uploads, config, and browser session
docker run --rm \
  -v relay_data:/data:ro \
  -v "${BACKUP_DIR}":/backup \
  alpine tar -czf "/backup/relay_backup_${TIMESTAMP}.tar.gz" -C /data .

# 3. Clean up temporary SQLite snapshot
docker exec relay-dispatcher rm -f /data/whatsapp_web_backup.db

# 4. Retain last 7 daily backups
find "${BACKUP_DIR}" -name "relay_backup_*.tar.gz" -mtime +7 -delete

echo "Backup created successfully: ${DEST_FILE}"
EOF

sudo chmod +x /usr/local/bin/backup-relay.sh
```

### Schedule Daily Backup
Add to root crontab:
```bash
sudo crontab -e
```
Add the line:
```text
0 3 * * * /usr/local/bin/backup-relay.sh > /var/log/relay_backup.log 2>&1
```

---

## 3. Disaster Recovery / Migration to a New Server

To migrate Relay to a new VM or restore after server failure:

### Step 3.1: Copy Backup Archive to Target Server
```bash
scp -i ~/.ssh/id_rsa /opt/relay-backups/relay_backup_latest.tar.gz ubuntu@<NEW_SERVER_IP>:/tmp/
```

### Step 3.2: Restore Into Docker Volume
On the new server:
```bash
# Ensure docker is installed and relay_data volume exists
docker volume create relay_data

# Extract backup archive directly into the Docker volume
docker run --rm \
  -v relay_data:/data \
  -v /tmp:/backup \
  alpine sh -c "cd /data && tar -xzf /backup/relay_backup_latest.tar.gz"
```

### Step 3.3: Deploy Relay
Deploy using Coolify or `docker compose -f compose.coolify.yml up -d`.
Relay will start with all contacts, campaigns, and WhatsApp Web authentication intact without re-pairing!
