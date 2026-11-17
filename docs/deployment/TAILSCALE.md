# Tailscale & Tailscale Serve &mdash; Private Cloud Access

This guide explains how to connect your Oracle Cloud VM and mobile phone to your private **Tailscale Tailnet**, enable automatic HTTPS via **MagicDNS**, and configure **Tailscale Serve** to proxy traffic to Relay.

---

## 1. What is Tailscale Serve?

- **Tailscale** creates an encrypted WireGuard mesh network connecting your devices regardless of physical location or firewall boundaries.
- **Tailscale Serve** lets your VM act as a private reverse proxy:
  - Terminates TLS with an official **Let's Encrypt certificate** issued for your machine's MagicDNS name (e.g. `https://relay.<tailnet-name>.ts.net`).
  - Proxies traffic privately to `http://127.0.0.1:8000`.
  - Injects verified user identity headers (`Tailscale-User-Login: you@gmail.com`).
  - **100% Private**: Only devices signed into your Tailscale account can access it.

> [!WARNING]
> **DO NOT USE `tailscale funnel`.**
> `tailscale funnel` opens your service to the entire public internet.
> `tailscale serve` keeps your service private to your authenticated Tailscale devices.

---

## 2. Installing Tailscale on the Oracle VM

Connect to your Oracle VM via SSH and run:

```bash
# 1. Install official Tailscale package
curl -fsSL https://tailscale.com/install.sh | sh

# 2. Authenticate the VM and enable Tailscale SSH
sudo tailscale up --ssh --hostname=relay
```

Tailscale will print an authentication URL:
```text
To authenticate, visit:
https://login.tailscale.com/a/0123456789abcdef
```
Open that link in your browser and approve the machine using your Google/GitHub account.

Verify connection:
```bash
tailscale status
```

---

## 3. Enable MagicDNS and HTTPS in Tailscale Console

1. Open the [Tailscale Admin Console](https://login.tailscale.com/admin/dns).
2. Go to the **DNS** tab:
   - Ensure **MagicDNS** is **Enabled**.
   - Under **HTTPS Certificates**, click **Enable HTTPS Certificates**.

---

## 4. Configure Tailscale Serve for Relay

Once Relay is running on `127.0.0.1:8000` (via Coolify or Docker Compose), run this single command on the Oracle VM:

```bash
# Configure Tailscale Serve to proxy HTTPS traffic to local port 8000
sudo tailscale serve https / http://127.0.0.1:8000
```

Verify the serve configuration:
```bash
tailscale serve status
```
Output:
```text
https://relay.your-tailnet.ts.net (tailnet only)
|-- / proxy http://127.0.0.1:8000
```

Tailscale Serve will automatically obtain a valid Let's Encrypt TLS certificate for `relay.your-tailnet.ts.net` and keep it renewed.

---

## 5. Tailscale Identity Headers

When you access `https://relay.your-tailnet.ts.net` through Tailscale Serve, the proxy automatically attaches:
- `Tailscale-User-Login`: e.g. `alice@gmail.com`
- `Tailscale-User-Name`: e.g. `Alice Smith`

Relay's `AuthMiddleware` automatically reads these headers and signs you in seamlessly.

To restrict access to only your email address:
In your Relay `.env` file, set:
```bash
ALLOWED_TAILSCALE_USERS=alice@gmail.com
```
Any other person in your tailnet attempting to access Relay will receive a 403 Forbidden response.
