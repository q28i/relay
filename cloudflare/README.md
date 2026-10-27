# Cloudflare Worker Update Server for WhatsApp Bulk Messenger Pro

This directory contains the edge worker for distributing updates, version checks, and download redirects globally with zero latency.

---

## 1-Click Deployment

1. Double-click **`deploy.bat`**:
   - Opens your browser to log into your Cloudflare account.
   - Deploys the worker to Cloudflare's edge network automatically.
2. Note your Worker URL (e.g. `https://whatsapp-bulk-updater.<subdomain>.workers.dev`).
3. Paste that URL into `update_config.json`:
   ```json
   {
       "provider": "cloudflare",
       "custom_endpoint": "https://whatsapp-bulk-updater.<subdomain>.workers.dev"
   }
   ```

---

## Direct Terminal Deployment

```powershell
cd cloudflare
npx wrangler login
npx wrangler deploy
```

---

## Connecting via Cloudflare Dashboard (Native GitHub Integration)

1. Go to your **[Cloudflare Dashboard](https://dash.cloudflare.com/)**.
2. Click **Compute (Workers) -> Workers & Pages -> Create Application**.
3. Select **Pages** or **Workers**, and choose **Connect to Git**.
4. Select your private GitHub repository: `ainttyug/whatsapp-bulk-messenger`.
5. Cloudflare will automatically build and deploy new updates every time you push to `main`!
