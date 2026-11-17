# Mobile Phone Access & WhatsApp Phone Pairing Guide

This guide explains how to access Relay from an iPhone (iOS) or Android smartphone, install it as a native-feeling Home Screen web app (PWA), and authenticate WhatsApp using the single-phone pairing code workflow.

---

## 1. Install Tailscale on Your Mobile Phone

1. Download the official **Tailscale** application:
   - **iOS (iPhone/iPad)**: [App Store](https://apps.apple.com/app/tailscale/id1470499037)
   - **Android**: [Google Play Store](https://play.google.com/store/apps/details?id=com.tailscale.ipn)
2. Open the Tailscale app and tap **Log in**.
3. Sign in using the same identity (Google, Microsoft, GitHub, or Apple) used on your Oracle Cloud server.
4. Toggle the VPN switch to **Connected**.
5. Verify that your `relay` server appears in the active machine list.

---

## 2. Access the Relay Dashboard

1. Open your mobile browser (**Safari** on iOS, **Chrome** on Android).
2. Navigate to your server's Tailscale HTTPS address:
   ```text
   https://relay.<your-tailnet-name>.ts.net
   ```
   *(Replace `<your-tailnet-name>` with your actual Tailnet name from the Tailscale app, e.g. `relay.manta-ray.ts.net`)*
3. Tailscale Serve terminates HTTPS with a valid Let's Encrypt certificate, displaying the secure lock icon 🔒.
4. Relay's `AuthMiddleware` verifies your Tailscale identity header and opens the dashboard directly without requiring a password prompt.

---

## 3. Install as a Progressive Web App (PWA)

Installing Relay to your Home Screen provides a fullscreen app experience without browser URL bars:

### On iPhone (Safari)
1. Tap the **Share** button (box with an upward arrow at the bottom).
2. Scroll down and tap **Add to Home Screen**.
3. Confirm the name **Relay** and tap **Add**.
4. Launch Relay directly from your Home Screen icon.

### On Android (Chrome)
1. Tap the **⋮ (three dots)** menu button in the top right.
2. Tap **Add to Home screen** or **Install app**.
3. Tap **Install**.
4. Open the installed Relay app from your app drawer.

---

## 4. Single-Phone WhatsApp Pairing Flow

Because you are using Relay directly from your phone, you cannot scan a QR code from the same screen. Follow this 60-second procedure:

### Step 4.1: Request Pairing Code in Relay
1. On the Relay dashboard, find the **Messaging Connection** card.
2. Tap **Link with Phone Number**.
3. In the modal, enter your mobile phone number including country code (e.g. `+14155552671` or `919876543210`).
4. Tap **Generate Pairing Code**.
5. Headless Chromium in the cloud connects to WhatsApp Web and generates an 8-character code (e.g. `K9W3-7H2R`).
6. Tap the **Copy Code** button.

### Step 4.2: Enter Code in WhatsApp
1. Open your regular **WhatsApp** mobile app.
2. Go to **Settings** (bottom right on iOS) or tap **⋮ (three dots)** &rarr; **Linked Devices** (Android).
3. Tap **Link a Device**.
4. When the camera scanner appears, look at the bottom of the screen and tap **Link with phone number instead**.
5. Paste or type the 8-character code.
6. WhatsApp will confirm device linking.

### Step 4.3: Return to Relay
1. Switch back to Relay on your phone.
2. The pairing modal automatically detects the active session and displays:
   `WhatsApp successfully connected!`
3. The dashboard status updates to **Connected**, and your contacts and templates are ready for dispatch 24/7!
