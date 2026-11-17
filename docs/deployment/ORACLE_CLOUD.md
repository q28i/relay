# Oracle Cloud Always Free &mdash; VM Setup Guide

This guide walks through creating and hardening an **Always Free Ampere A1 (ARM64)** Compute Instance on Oracle Cloud Infrastructure (OCI).

---

## 1. Always Free Tier Entitlements

Oracle Cloud provides one of the most generous permanent free tiers in cloud computing:
- **Architecture**: Arm-based Ampere A1 Compute
- **OCPUs**: Up to 4 cores (shared or single instance)
- **Memory**: Up to 24 GB RAM
- **Boot Volume**: Up to 200 GB storage across instances
- **Cost**: **$0.00 / month forever** (within Always Free limits)

---

## 2. Step-by-Step Instance Creation

### Step 2.1: Open Compute Console
1. Log into your [Oracle Cloud Console](https://cloud.oracle.com).
2. Open the navigation menu &rarr; **Compute** &rarr; **Instances**.
3. Click **Create instance**.

### Step 2.2: Configure Instance Details
- **Name**: `relay-cloud-server`
- **Compartment**: (Your root or default compartment)
- **Placement**: Keep default Availability Domain.

### Step 2.3: Image and Shape
1. Click **Change image**:
   - Select **Canonical Ubuntu**.
   - Choose **Ubuntu 24.04 Minimal** or **Ubuntu 22.04 LTS**.
2. Click **Change shape**:
   - Shape series: **Ampere (Arm-based Processor)**.
   - Select **VM.Standard.A1.Flex**.
   - Configure resources:
     - **OCPUs**: `4` (or `2` if sharing with another VM)
     - **Memory**: `24` GB (or `12` GB)
   - Verify the **"Always Free Eligible"** badge is shown.

### Step 2.4: Networking (VCN)
1. Select **Create new virtual cloud network** (or use existing default VCN).
2. Ensure **Assign a public IPv4 address** is checked (needed for initial SSH and outbound internet access).

### Step 2.5: Add SSH Keys
1. Under **Add SSH keys**, select **Generate a key pair for me** (and download both private and public keys) OR paste your existing public SSH key (`id_ed25519.pub` or `id_rsa.pub`).
2. **Important**: Save the downloaded `.key` file safely.

### Step 2.6: Boot Volume
- Keep default **50 GB** or increase up to **150 GB** (Always Free tier includes up to 200 GB total across all instances).

### Step 2.7: Launch
Click **Create**. The instance status will turn from *Provisioning* to *Running* within 1–2 minutes. Note the **Public IP Address**.

---

## 3. Initial SSH Connection and Hardening

### Connect via SSH
From your local terminal:
```bash
# Set strict permissions on private key
chmod 400 ~/path/to/ssh-key.key

# Connect as ubuntu user
ssh -i ~/path/to/ssh-key.key ubuntu@<YOUR_ORACLE_PUBLIC_IP>
```

### Update System Packages
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl ufw ca-certificates htop
```

### Configure Host Firewall (`ufw`)
By default, Oracle Cloud Ubuntu images include `iptables` rules that may conflict with Docker. Configure `ufw` cleanly:

```bash
# Allow SSH so you don't lock yourself out
sudo ufw allow 22/tcp comment "SSH administration"

# Allow all traffic on the private Tailscale interface
sudo ufw allow in on tailscale0

# Set default policies (Deny incoming, Allow outgoing)
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Enable ufw
sudo ufw enable
sudo ufw status verbose
```

> [!IMPORTANT]
> **Do NOT open port 8000 on the Oracle VCN Security List or ufw.**
> Relay will only listen on `127.0.0.1:8000`. All access will flow securely through Tailscale on the `tailscale0` network interface.
