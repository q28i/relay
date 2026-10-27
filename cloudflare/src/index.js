/**
 * Cloudflare Worker: WhatsApp Bulk Messenger Pro Update & Distribution API
 * Serves version manifest and redirects clients to the latest release assets.
 */

const DEFAULT_MANIFEST = {
  version: "1.2.0",
  release_date: "2026-10-27",
  min_python_version: "3.8",
  developer_device: "DEV-A723A0AA431176BD",
  changelog: [
    "Added In-App Excel Sheet Editor with Real-time Editing & Quick-Paste",
    "Added Hardware Device ID Identification & Developer Whitelist Logging",
    "Added Auto-Updater with GitHub & Cloudflare remote distribution",
    "Dual GUI mode: Simplified 3-step dashboard & Power-user Developer Mode",
    "Sanitized codebase for shipping with 1-click Python & dependency installer"
  ],
  download_url: "https://github.com/ainttyug/whatsapp-bulk-messenger/releases/download/v1.2.0/whatsapp-bulk-messenger-v1.2.0.zip",
  asset_name: "whatsapp-bulk-messenger-v1.2.0.zip",
  sha256: "45709308e746a1476db841f3e7d56a29be8534c03b879ec36437fe6cf58fe53b"
};

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, HEAD, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    // Health check root
    if (path === "/" || path === "/health") {
      return new Response(JSON.stringify({
        status: "online",
        service: "WhatsApp Bulk Messenger Pro Update Server",
        version: env.CURRENT_VERSION || DEFAULT_MANIFEST.version,
        time: new Date().toISOString()
      }, null, 2), {
        headers: {
          "Content-Type": "application/json",
          ...corsHeaders
        }
      });
    }

    // Version manifest endpoint
    if (path === "/version.json") {
      const manifest = {
        ...DEFAULT_MANIFEST,
        version: env.CURRENT_VERSION || DEFAULT_MANIFEST.version
      };
      return new Response(JSON.stringify(manifest, null, 2), {
        headers: {
          "Content-Type": "application/json",
          "Cache-Control": "public, max-age=60",
          ...corsHeaders
        }
      });
    }

    // Direct download redirect
    if (path === "/download" || path === "/latest.zip") {
      const downloadTarget = DEFAULT_MANIFEST.download_url;
      return Response.redirect(downloadTarget, 302);
    }

    return new Response(JSON.stringify({ error: "Not Found", available_endpoints: ["/version.json", "/download", "/health"] }), {
      status: 404,
      headers: { "Content-Type": "application/json", ...corsHeaders }
    });
  }
};
