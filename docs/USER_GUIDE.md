# Relay Operator & User Guide

This guide provides practical, step-by-step instructions for operating Relay's Web Dashboard. Every procedure reflects the active interface controls.

---

## 1. System Startup & Access

1. Open PowerShell or Command Prompt in the Relay project root.
2. Launch the backend server:
   ```bash
   python web_run.py --no-browser
   ```
   *(Or double-click `start_dashboard.bat` if configured on Windows).*
3. Open your web browser and navigate to:
   ```text
   http://127.0.0.1:8000
   ```

---

## 2. Connecting WhatsApp Web

1. In the top navigation bar or **Dashboard**, observe the **Browser Connection Card**.
2. By default, Relay targets the **Relay Automation Session (Persistent & Supported)** (`__dedicated__`).
3. Click **Start Relay Session** (or **Restart Session** if resolving a conflict).
4. A dedicated Chrome browser window will open and navigate to `https://web.whatsapp.com`.
5. **Initial Authentication**:
   - If this is your first launch, a QR code appears in the Chrome window.
   - Open WhatsApp on your mobile phone &rarr; **Settings** &rarr; **Linked Devices** &rarr; **Link a Device**.
   - Point your phone's camera at the QR code.
6. Once authenticated, Relay transitions to **Active in Relay** (green badge).
7. **Session Persistence**: Credentials remain saved in `whatsapp_browser_session/`. On subsequent restarts, WhatsApp reconnects automatically without scanning the QR code again.

---

## 3. Managing Contacts

1. Navigate to the **Contacts** tab in the sidebar.
2. **Importing Contacts**:
   - Click **Import Contacts**.
   - Drag and drop or browse for a `.csv`, `.xlsx`, or `.xls` file containing customer numbers and names.
   - The file should include columns such as `Phone` and `Name`.
   - Click **Commit Upload**. Numbers are automatically formatted into international standard (country code + number) and validated.
3. **Opt-Out / Suppression List**:
   - To view blocked numbers, click **View Blocked / Opt-Outs**.
   - Any number on this list is permanently skipped during campaigns to prevent unwanted messaging.

---

## 4. Creating & Saving Templates

1. Navigate to the **Templates** tab.
2. Click **New Template**.
3. Enter a **Template Title** (e.g., `Product Announcement`).
4. **Attaching Media**:
   - Click **Attach Media**.
   - Select an approved image (`.jpg`, `.png`, `.jpeg`) from your Media Library or upload a new business photo.
5. **Adding Text Variations**:
   - Relay supports multiple message variations to prevent sending identical texts.
   - Enter your message in the text editor.
   - Click **Add Variation** to create alternative phrasings.
6. **Using Dynamic Variables**:
   - Insert `{name}` to personalize the greeting (e.g., `Hello {name}, your order is ready!`).
   - Use Spintax patterns like `{Hi|Hello|Hey}` to ensure organic variation.
7. **Saving**:
   - Click **Save Template**. The template is persisted directly into SQLite and is immediately available for campaigns.

---

## 5. Launching an Authorized Campaign

1. Navigate to the **Campaigns** tab.
2. Click **Create Campaign**.
3. **Step 1: Select Template**: Choose your saved template.
4. **Step 2: Select Recipients**:
   - Choose a contact group or select specific verified contacts.
5. **Step 3: Choose Sending Format**:
   - **Image with caption (Recommended)**: Sends the photo and text together as a single unified message bubble.
   - **Image followed by text**: Sends the photo first, then sends the text as a separate bubble.
6. **Step 4: Pacing & Anti-Ban Safeguards**:
   - Configure **Min Delay** (default: `8.0s`) and **Max Delay** (default: `15.0s`).
   - Configure **Batch Size** (default: `20`) and **Batch Cooldown Pause** (default: `60s`).
7. **Step 5: Preview Assignments**:
   - Review how each recipient will be resolved (personalized text, assigned media).
8. **Step 6: Launch**:
   - Click **Launch Campaign**. The campaign enters the durable job queue.

---

## 6. Monitoring & Activity Inspection

1. **Top Bar Global Banner**:
   - Appears during active execution showing the campaign name, progress counter (`X / Y sent`), and progress bar.
2. **Activity Drawer**:
   - Click on the **Activity** tab to see every processed recipient.
   - Click on any recipient row to slide open the **Recipient Activity Detail Drawer**:
     - **Media Status**: `SENT`, `SKIPPED`, `FAILED`, or `UNCERTAIN`.
     - **Text Status**: `SENT`, `SKIPPED`, `FAILED`, or `UNCERTAIN`.
     - **Overall Status**: `DISPATCHED`, `PARTIALLY_SENT`, or `UNCERTAIN`.
     - **Error Details**: Full diagnostic reason if an issue occurred.

---

## 7. Pausing, Resuming, and Handling Uncertain Sends

### 7.1 Operator Pause
- Click **Pause** in the top banner at any time to halt outgoing dispatches.
- The worker finishes the current recipient cleanly, then halts.
- Click **Resume** to continue.

### 7.2 Automatic Pause on `RECONCILIATION_REQUIRED`
- If Relay encounters an unconfirmed send (e.g. browser overlay lingered or network stalled), the campaign transitions automatically to **Reconciliation Required** (amber badge).
- **Required Action**:
  1. Inspect the real WhatsApp Web window to verify whether the recipient received the photo.
  2. If the message was received: Note the delivery in your logs.
  3. Click **Resume** in Relay to proceed to the next recipient without re-sending the uncertain message.

---

## 8. Troubleshooting Common Issues

| Issue | Cause | Solution |
|---|---|---|
| **"Selected profile is currently open in Chrome"** | A personal Chrome window is running on the selected user profile. | Switch to the dedicated session (`__dedicated__`) or close open Chrome windows. |
| **"Cannot reach Relay server"** | FastAPI backend process is not running. | Run `python web_run.py --no-browser` in your terminal. |
| **"Number not registered on WhatsApp"** | The phone number does not have a WhatsApp account. | Relay marks the recipient `FAILED_PERMANENT` and advances automatically. |
| **Media preview does not open** | Image file moved or 0 bytes. | Verify file exists in `uploads/media/` and is valid JPEG/PNG. |
