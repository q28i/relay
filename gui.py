"""
WhatsApp Bulk Messenger Pro - Modern GUI
Features:
- Simplified, user-friendly 3-step dashboard for non-technical users (Default Mode)
- Built-in Excel & Contacts Spreadsheet Editor powered by tksheet (Add, edit, quick-paste numbers directly)
- Full Developer Mode toggle for power users (Advanced browser profiles, custom cooldown sliders, live data tables, scheduler)
- Shared data model between Simple and Developer views
- Seamless 1-click execution with persistent configuration
"""

import os
import sys
import time
import threading
import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from browser_manager import BrowserManager
from data_loader import DataLoader
from whatsapp_engine import WhatsAppEngine, process_spintax
from excel_editor import ExcelEditorDialog
from device_manager import DeviceManager
from updater import Updater

CONFIG_FILE = "config.json"


class WhatsAppGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("WhatsApp Bulk Messenger Pro")
        self.geometry("780x690")
        self.minsize(720, 600)

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.engine = None
        self.driver = None
        self.worker_thread = None
        self.loaded_contacts = []
        self.is_running = False
        self.current_profiles = []

        # Device & Licensing Identification
        self.device_info = DeviceManager.get_device_info()
        self.app_version = Updater.get_current_version()
        DeviceManager.log_device_startup(self.app_version)
        DeviceManager.save_auth_config()

        # Update Variables
        self.update_cfg = Updater.load_update_config()
        self.repo_var = tk.StringVar(value=self.update_cfg.get("github_repo", "ainttyug/whatsapp-bulk-messenger"))
        self.branch_var = tk.StringVar(value=self.update_cfg.get("branch", "main"))
        self.endpoint_var = tk.StringVar(value=self.update_cfg.get("custom_endpoint", ""))
        self.auto_check_var = tk.BooleanVar(value=self.update_cfg.get("auto_check_on_startup", True))
        self.new_ver_var = tk.StringVar(value="1.2.1")
        self.is_checking_update = False

        # Shared Variables
        self.file_path_var = tk.StringVar()
        self.cc_var = tk.StringVar(value="")
        self.attach_enabled_var = tk.BooleanVar(value=False)
        self.attach_path_var = tk.StringVar()
        self.browser_var = tk.StringVar(value="chrome")
        self.headless_var = tk.BooleanVar(value=False)
        self.dev_mode_var = tk.BooleanVar(value=False)

        # Anti-ban variables
        self.min_delay_var = tk.DoubleVar(value=8.0)
        self.max_delay_var = tk.DoubleVar(value=15.0)
        self.batch_size_var = tk.IntVar(value=20)
        self.batch_pause_var = tk.DoubleVar(value=60.0)
        self.daily_cap_var = tk.IntVar(value=100)

        # Scheduler variables
        self.sched_enabled_var = tk.BooleanVar(value=False)
        self.sched_time_var = tk.StringVar(value="09:30")

        self.prog_var = tk.DoubleVar(value=0)

        self._apply_styles()
        self._build_top_header()

        # Containers for both modes
        self.main_container = ttk.Frame(self)
        self.main_container.pack(fill="both", expand=True, padx=15, pady=5)

        self.simple_frame = ttk.Frame(self.main_container)
        self.dev_frame = ttk.Frame(self.main_container)

        self._build_simple_ui()
        self._build_dev_ui()
        self._build_bottom_controls()

        self._load_saved_config()
        self._toggle_mode_view()

        if self.auto_check_var.get():
            self.after(2500, lambda: self._check_updates_gui(prompt_if_current=False))

    def _apply_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground="#128C7E")
        style.configure("SubHeader.TLabel", font=("Segoe UI", 9), foreground="#555555")
        style.configure("StepTitle.TLabel", font=("Segoe UI", 10, "bold"), foreground="#075E54")
        style.configure("Card.TLabelframe", padding=10)
        style.configure("Card.TLabelframe.Label", font=("Segoe UI", 10, "bold"), foreground="#128C7E")
        style.configure("BigAction.TButton", font=("Segoe UI", 11, "bold"), padding=[15, 8])
        style.configure("Action.TButton", font=("Segoe UI", 9, "bold"))
        style.configure("Small.TButton", font=("Segoe UI", 9))
        style.configure("TNotebook.Tab", font=("Segoe UI", 9, "bold"), padding=[10, 5])
        style.configure("BadgeDev.TLabel", font=("Segoe UI", 8, "bold"), foreground="#B8860B", background="#FFF8DC", padding=[4, 2])
        style.configure("BadgeClient.TLabel", font=("Segoe UI", 8, "bold"), foreground="#0066cc", background="#E6F2FF", padding=[4, 2])
        style.configure("BadgeId.TLabel", font=("Segoe UI", 8), foreground="#444444", background="#F0F0F0", padding=[4, 2])

    def _build_top_header(self):
        header = ttk.Frame(self, padding="15 8 15 6")
        header.pack(fill="x")

        # Top row: Title and Dev mode toggle
        top_row = ttk.Frame(header)
        top_row.pack(fill="x")

        left = ttk.Frame(top_row)
        left.pack(side="left")
        ttk.Label(left, text="WhatsApp Bulk Messenger Pro", style="Header.TLabel").pack(anchor="w")
        ttk.Label(left, text="Send personalized messages & media directly to your contacts", style="SubHeader.TLabel").pack(anchor="w")

        right = ttk.Frame(top_row)
        right.pack(side="right", anchor="e")
        chk_dev = ttk.Checkbutton(right, text="🛠️ Developer Mode", variable=self.dev_mode_var, command=self._toggle_mode_view)
        chk_dev.pack(anchor="e")
        ttk.Label(right, text="(Show advanced controls)", font=("Segoe UI", 8), foreground="#888").pack(anchor="e")

        # Sub-bar: Device ID badge, Role badge, Version, and Check Updates button
        badge_bar = ttk.Frame(header)
        badge_bar.pack(fill="x", pady=(6, 0))

        b_left = ttk.Frame(badge_bar)
        b_left.pack(side="left")

        ttk.Label(b_left, text=f"Device: {self.device_info['short_id']}", style="BadgeId.TLabel").pack(side="left", padx=(0, 4))
        self.btn_copy_id = ttk.Button(b_left, text="📋 Copy", style="Small.TButton", command=self._copy_device_id)
        self.btn_copy_id.pack(side="left", padx=(0, 8))

        if self.device_info["is_developer"]:
            ttk.Label(b_left, text="👑 DEVELOPER", style="BadgeDev.TLabel").pack(side="left", padx=(0, 8))
        else:
            ttk.Label(b_left, text="👤 CLIENT", style="BadgeClient.TLabel").pack(side="left", padx=(0, 8))

        ttk.Label(b_left, text=f"v{self.app_version}", font=("Segoe UI", 8, "italic"), foreground="#777").pack(side="left")

        b_right = ttk.Frame(badge_bar)
        b_right.pack(side="right")
        self.btn_check_update = ttk.Button(b_right, text="🔄 Check for Updates", style="Small.TButton", command=lambda: self._check_updates_gui(prompt_if_current=True))
        self.btn_check_update.pack(side="right")
        self.update_header_lbl = ttk.Label(b_right, text="", font=("Segoe UI", 8), foreground="#128C7E")
        self.update_header_lbl.pack(side="right", padx=6)

    def _toggle_mode_view(self):
        if self.dev_mode_var.get():
            self.simple_frame.pack_forget()
            self.dev_frame.pack(fill="both", expand=True)
            self.geometry("980x740")
            self._sync_simple_to_dev()
        else:
            self.dev_frame.pack_forget()
            self.simple_frame.pack(fill="both", expand=True)
            self.geometry("780x680")
            self._sync_dev_to_simple()

    # =========================================================================
    # 1. SIMPLIFIED VIEW (For Everyday / Non-Technical Users)
    # =========================================================================
    def _build_simple_ui(self):
        # Step 1: Contacts Card
        card_contacts = ttk.LabelFrame(self.simple_frame, text="Step 1: Choose Your Contacts List", style="Card.TLabelframe")
        card_contacts.pack(fill="x", pady=6)

        c_row1 = ttk.Frame(card_contacts)
        c_row1.pack(fill="x", pady=2)
        ttk.Button(c_row1, text="📂 Select Excel / CSV File...", command=self._browse_contacts_file).pack(side="left", padx=(0, 6))
        ttk.Button(c_row1, text="📊 Open Built-in Excel Editor (Add/Edit Contacts)", style="Action.TButton", command=self.open_excel_editor).pack(side="left", padx=(0, 6))
        ttk.Button(c_row1, text="📄 View Template", style="Small.TButton", command=self._open_sample_template).pack(side="left")

        self.simple_file_status = ttk.Label(card_contacts, text="No file selected. Click 'Select File' or 'Open Built-in Excel Editor' to start.", font=("Segoe UI", 9, "bold"), foreground="#555")
        self.simple_file_status.pack(anchor="w", pady=(6, 0))

        # Step 2: Message Card
        card_msg = ttk.LabelFrame(self.simple_frame, text="Step 2: Type Your Message", style="Card.TLabelframe")
        card_msg.pack(fill="x", pady=6)

        m_bar = ttk.Frame(card_msg)
        m_bar.pack(fill="x", pady=(0, 4))
        ttk.Label(m_bar, text="Insert name tags:").pack(side="left", padx=(0, 5))
        ttk.Button(m_bar, text="+ Contact Name", style="Small.TButton", command=lambda: self._insert_simple_tag("{name}")).pack(side="left", padx=2)
        ttk.Button(m_bar, text="+ First Name", style="Small.TButton", command=lambda: self._insert_simple_tag("{first_name}")).pack(side="left", padx=2)

        self.simple_msg_text = tk.Text(card_msg, height=4, font=("Segoe UI", 10), wrap="word")
        self.simple_msg_text.pack(fill="x", pady=2)
        self.simple_msg_text.insert("1.0", "Hello {name}, thank you for connecting with us! Here is your update.")

        ttk.Label(card_msg, text="💡 Tip: '{name}' will automatically change to each customer's real name.", font=("Segoe UI", 8), foreground="#666").pack(anchor="w")

        # Step 3: Media Attachment Card (Optional)
        card_media = ttk.LabelFrame(self.simple_frame, text="Step 3: Attach a Photo, Video, or Document (Optional)", style="Card.TLabelframe")
        card_media.pack(fill="x", pady=6)

        med_row = ttk.Frame(card_media)
        med_row.pack(fill="x", pady=2)
        ttk.Button(med_row, text="📎 Select Picture, Video, or PDF...", command=self._browse_media_file).pack(side="left", padx=(0, 8))
        self.simple_btn_remove_media = ttk.Button(med_row, text="❌ Remove Attachment", style="Small.TButton", command=self._clear_media_file, state="disabled")
        self.simple_btn_remove_media.pack(side="left")

        self.simple_media_status = ttk.Label(card_media, text="No attachment selected (Text message only).", font=("Segoe UI", 9), foreground="#666")
        self.simple_media_status.pack(anchor="w", pady=(4, 0))

    def open_excel_editor(self):
        curr_file = self.file_path_var.get().strip()
        if not curr_file or not os.path.isfile(curr_file):
            curr_file = os.path.join(self.base_dir, "contacts_sample.xlsx")
            DataLoader.create_sample_files_if_needed(self.base_dir)

        def on_saved(saved_path, total_rows):
            self.file_path_var.set(saved_path)
            self._reload_contacts_data()

        ExcelEditorDialog(self, current_file=curr_file, on_saved_callback=on_saved)

    def _open_sample_template(self):
        sample_path = os.path.join(self.base_dir, "contacts_sample.xlsx")
        DataLoader.create_sample_files_if_needed(self.base_dir)
        if os.path.isfile(sample_path):
            try:
                os.startfile(sample_path)
            except Exception:
                os.system(f'explorer "{sample_path}"')

    def _insert_simple_tag(self, tag: str):
        self.simple_msg_text.insert(tk.INSERT, tag)

    def _clear_media_file(self):
        self.attach_path_var.set("")
        self.attach_enabled_var.set(False)
        self.simple_media_status.config(text="No attachment selected (Text message only).", foreground="#666")
        self.simple_btn_remove_media.config(state="disabled")

    # =========================================================================
    # 2. DEVELOPER VIEW (For Power Users / Advanced Configuration)
    # =========================================================================
    def _build_dev_ui(self):
        self.dev_notebook = ttk.Notebook(self.dev_frame)
        self.dev_notebook.pack(fill="both", expand=True, pady=5)

        self.dtab_contacts = ttk.Frame(self.dev_notebook, padding=10)
        self.dtab_message = ttk.Frame(self.dev_notebook, padding=10)
        self.dtab_browser = ttk.Frame(self.dev_notebook, padding=10)
        self.dtab_cooldown = ttk.Frame(self.dev_notebook, padding=10)
        self.dtab_scheduler = ttk.Frame(self.dev_notebook, padding=10)
        self.dtab_updates = ttk.Frame(self.dev_notebook, padding=10)

        self.dev_notebook.add(self.dtab_contacts, text="  📁 Contacts Data  ")
        self.dev_notebook.add(self.dtab_message, text="  ✉️ Message & Spintax  ")
        self.dev_notebook.add(self.dtab_browser, text="  🌐 Browser & Profiles  ")
        self.dev_notebook.add(self.dtab_cooldown, text="  🛡️ Cooldown & Safety  ")
        self.dev_notebook.add(self.dtab_scheduler, text="  ⏰ Daily Scheduler  ")
        self.dev_notebook.add(self.dtab_updates, text="  🚀 Updates & Publishing  ")

        self._build_dev_contacts_tab()
        self._build_dev_message_tab()
        self._build_dev_browser_tab()
        self._build_dev_cooldown_tab()
        self._build_dev_scheduler_tab()
        self._build_dev_updates_tab()

    def _build_dev_contacts_tab(self):
        top_bar = ttk.Frame(self.dtab_contacts)
        top_bar.pack(fill="x", pady=2)
        ttk.Label(top_bar, text="File:").pack(side="left", padx=2)
        ttk.Entry(top_bar, textvariable=self.file_path_var, width=42).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(top_bar, text="Browse...", command=self._browse_contacts_file).pack(side="left", padx=2)
        ttk.Button(top_bar, text="📊 Open Excel Editor", style="Action.TButton", command=self.open_excel_editor).pack(side="left", padx=2)
        ttk.Button(top_bar, text="Reload", command=self._reload_contacts_data).pack(side="left", padx=2)

        s_bar = ttk.Frame(self.dtab_contacts)
        s_bar.pack(fill="x", pady=4)
        ttk.Label(s_bar, text="Default Country Code:").pack(side="left", padx=2)
        ttk.Entry(s_bar, textvariable=self.cc_var, width=8).pack(side="left", padx=5)
        ttk.Label(s_bar, text="(Prepends to 10-digit numbers e.g. 91)", font=("Segoe UI", 8), foreground="#666").pack(side="left")

        # Table
        t_frame = ttk.Frame(self.dtab_contacts)
        t_frame.pack(fill="both", expand=True, pady=4)
        cols = ("phone", "name", "custom_msg", "attachment")
        self.dev_tree = ttk.Treeview(t_frame, columns=cols, show="headings", height=8)
        self.dev_tree.heading("phone", text="Phone Number")
        self.dev_tree.heading("name", text="Recipient Name")
        self.dev_tree.heading("custom_msg", text="Message Preview")
        self.dev_tree.heading("attachment", text="Row Attachment")
        self.dev_tree.column("phone", width=130)
        self.dev_tree.column("name", width=130)
        self.dev_tree.column("custom_msg", width=300)
        self.dev_tree.column("attachment", width=150)

        sb = ttk.Scrollbar(t_frame, orient="vertical", command=self.dev_tree.yview)
        self.dev_tree.configure(yscrollcommand=sb.set)
        self.dev_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.dev_contact_count_lbl = ttk.Label(self.dtab_contacts, text="Total Loaded: 0 contacts", font=("Segoe UI", 9, "bold"))
        self.dev_contact_count_lbl.pack(anchor="w", pady=2)

    def _build_dev_message_tab(self):
        t_bar = ttk.Frame(self.dtab_message)
        t_bar.pack(fill="x", pady=2)
        ttk.Label(t_bar, text="Quick Insert:").pack(side="left", padx=2)
        ttk.Button(t_bar, text="+ {name}", command=lambda: self._insert_dev_tag("{name}")).pack(side="left", padx=2)
        ttk.Button(t_bar, text="+ {first_name}", command=lambda: self._insert_dev_tag("{first_name}")).pack(side="left", padx=2)
        ttk.Button(t_bar, text="+ {phone}", command=lambda: self._insert_dev_tag("{phone}")).pack(side="left", padx=2)
        ttk.Button(t_bar, text="+ Spintax {Hi|Hello|Hey}", command=lambda: self._insert_dev_tag("{Hi|Hello|Hey} ")).pack(side="left", padx=2)
        ttk.Button(t_bar, text="Test Spintax", command=self._preview_spintax).pack(side="right", padx=5)

        self.dev_msg_text = tk.Text(self.dtab_message, height=6, font=("Segoe UI", 10), wrap="word")
        self.dev_msg_text.pack(fill="both", expand=True, pady=4)

        # Attachment Box
        att_box = ttk.LabelFrame(self.dtab_message, text="Attachment File Settings", padding=8)
        att_box.pack(fill="x", pady=6)
        ttk.Checkbutton(att_box, text="Enable Global Attachment", variable=self.attach_enabled_var).pack(anchor="w")
        arow = ttk.Frame(att_box)
        arow.pack(fill="x", pady=3)
        ttk.Entry(arow, textvariable=self.attach_path_var).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(arow, text="Browse...", command=self._browse_media_file).pack(side="left")

    def _insert_dev_tag(self, tag: str):
        self.dev_msg_text.insert(tk.INSERT, tag)

    def _preview_spintax(self):
        raw = self.dev_msg_text.get("1.0", "end-1c")
        sample = process_spintax(raw).replace("{name}", "Alex Mercer").replace("{first_name}", "Alex").replace("{phone}", "919876543210")
        messagebox.showinfo("Spintax Live Preview", f"Sample generated message:\n\n\"{sample}\"\n\nEach recipient gets a unique random variation!")

    def _build_dev_browser_tab(self):
        ttk.Label(self.dtab_browser, text="Target Browser:", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        self.installed_browsers = BrowserManager.get_installed_browsers()
        b_keys = list(self.installed_browsers.keys()) if self.installed_browsers else ["chrome"]

        b_row = ttk.Frame(self.dtab_browser)
        b_row.pack(fill="x", pady=2)
        for b in b_keys:
            name = self.installed_browsers.get(b, {}).get("name", b.title())
            ttk.Radiobutton(b_row, text=name, value=b, variable=self.browser_var, command=self._refresh_profiles).pack(side="left", padx=12)

        ttk.Label(self.dtab_browser, text="Browser Profile (Persistent Session):", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(12, 4))
        self.profile_combo = ttk.Combobox(self.dtab_browser, state="readonly", width=70)
        self.profile_combo.pack(anchor="w", pady=4)
        self._refresh_profiles()

        ttk.Checkbutton(self.dtab_browser, text="Run Headless (Background - No visible browser window)", variable=self.headless_var).pack(anchor="w", pady=10)

    def _refresh_profiles(self):
        b = self.browser_var.get()
        profiles = BrowserManager.get_profiles(b)
        self.current_profiles = profiles
        names = [p["name"] for p in profiles]
        self.profile_combo["values"] = names
        if names:
            self.profile_combo.current(0)

    def _build_dev_cooldown_tab(self):
        ttk.Label(self.dtab_cooldown, text="Reddit Anti-Ban Cooldown Controls", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        p_frame = ttk.LabelFrame(self.dtab_cooldown, text="Presets", padding=8)
        p_frame.pack(fill="x", pady=4)

        ttk.Button(p_frame, text="🛡️ Safe (12-20s, Batch 15, Pause 90s, Max 30/day)", command=self._apply_preset_safe).pack(anchor="w", pady=2)
        ttk.Button(p_frame, text="⚖️ Balanced (8-15s, Batch 20, Pause 60s, Max 100/day)", command=self._apply_preset_balanced).pack(anchor="w", pady=2)
        ttk.Button(p_frame, text="⚡ Fast (4-8s, Batch 30, Pause 30s)", command=self._apply_preset_fast).pack(anchor="w", pady=2)

        c_frame = ttk.LabelFrame(self.dtab_cooldown, text="Custom Pacing", padding=8)
        c_frame.pack(fill="x", pady=6)
        grid = ttk.Frame(c_frame)
        grid.pack(fill="x")

        ttk.Label(grid, text="Min Delay:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=self.min_delay_var, width=8).grid(row=0, column=1, padx=6, pady=2)
        ttk.Label(grid, text="sec").grid(row=0, column=2, sticky="w")

        ttk.Label(grid, text="Max Delay:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=self.max_delay_var, width=8).grid(row=1, column=1, padx=6, pady=2)
        ttk.Label(grid, text="sec (jitter)").grid(row=1, column=2, sticky="w")

        ttk.Label(grid, text="Batch Size:").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=self.batch_size_var, width=8).grid(row=2, column=1, padx=6, pady=2)
        ttk.Label(grid, text="msgs").grid(row=2, column=2, sticky="w")

        ttk.Label(grid, text="Batch Pause:").grid(row=3, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=self.batch_pause_var, width=8).grid(row=3, column=1, padx=6, pady=2)
        ttk.Label(grid, text="sec").grid(row=3, column=2, sticky="w")

        ttk.Label(grid, text="Daily Cap:").grid(row=4, column=0, sticky="w", pady=2)
        ttk.Entry(grid, textvariable=self.daily_cap_var, width=8).grid(row=4, column=1, padx=6, pady=2)
        ttk.Label(grid, text="max").grid(row=4, column=2, sticky="w")

    def _apply_preset_safe(self):
        self.min_delay_var.set(12.0)
        self.max_delay_var.set(20.0)
        self.batch_size_var.set(15)
        self.batch_pause_var.set(90.0)
        self.daily_cap_var.set(30)
        messagebox.showinfo("Safe Preset", "Safe Warm-up preset applied (ideal for new SIMs).")

    def _apply_preset_balanced(self):
        self.min_delay_var.set(8.0)
        self.max_delay_var.set(15.0)
        self.batch_size_var.set(20)
        self.batch_pause_var.set(60.0)
        self.daily_cap_var.set(100)
        messagebox.showinfo("Balanced Preset", "Balanced preset applied (standard recommended).")

    def _apply_preset_fast(self):
        self.min_delay_var.set(4.0)
        self.max_delay_var.set(8.0)
        self.batch_size_var.set(30)
        self.batch_pause_var.set(30.0)
        self.daily_cap_var.set(200)

    def _build_dev_scheduler_tab(self):
        ttk.Checkbutton(self.dtab_scheduler, text="Enable Daily Recurring Automation", variable=self.sched_enabled_var).pack(anchor="w", pady=5)
        srow = ttk.Frame(self.dtab_scheduler)
        srow.pack(fill="x", pady=6)
        ttk.Label(srow, text="Trigger Daily at (HH:MM):").pack(side="left", padx=5)
        ttk.Entry(srow, textvariable=self.sched_time_var, width=10).pack(side="left", padx=5)
        ttk.Label(srow, text="(24-hour format e.g. 09:30 or 14:00)").pack(side="left")

    def _build_dev_updates_tab(self):
        # 1. Device Identification
        dev_card = ttk.LabelFrame(self.dtab_updates, text="Hardware Identification & Security Audit", padding=10)
        dev_card.pack(fill="x", pady=4)

        g = ttk.Frame(dev_card)
        g.pack(fill="x")

        ttk.Label(g, text="Hardware Short ID:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(g, text=self.device_info["short_id"], font=("Consolas", 10, "bold"), foreground="#0066cc").grid(row=0, column=1, sticky="w", padx=8, pady=2)
        ttk.Button(g, text="📋 Copy ID", style="Small.TButton", command=lambda: self._copy_device_id(full=False)).grid(row=0, column=2, sticky="w", padx=4)

        ttk.Label(g, text="Full Hardware GUID:", font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Label(g, text=self.device_info["raw_guid"], font=("Consolas", 8), foreground="#555555").grid(row=1, column=1, sticky="w", padx=8, pady=2)
        ttk.Button(g, text="📋 Copy Full", style="Small.TButton", command=lambda: self._copy_device_id(full=True)).grid(row=1, column=2, sticky="w", padx=4)

        ttk.Label(g, text="Machine & OS:", font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Label(g, text=f"{self.device_info['machine_name']} | {self.device_info['os']}", font=("Segoe UI", 9)).grid(row=2, column=1, columnspan=2, sticky="w", padx=8, pady=2)

        ttk.Label(g, text="Access Role:", font=("Segoe UI", 9, "bold")).grid(row=3, column=0, sticky="w", pady=2)
        role_desc = "👑 Whitelisted Developer (Master Publishing Access)" if self.device_info["is_developer"] else "👤 Authorized Client Device"
        role_color = "#B8860B" if self.device_info["is_developer"] else "#0066cc"
        ttk.Label(g, text=role_desc, font=("Segoe UI", 9, "bold"), foreground=role_color).grid(row=3, column=1, columnspan=2, sticky="w", padx=8, pady=2)

        act_row = ttk.Frame(dev_card)
        act_row.pack(fill="x", pady=(8, 0))
        ttk.Button(act_row, text="📜 Open Audit Trace Log (device_audit.log)", style="Small.TButton", command=self._open_audit_log).pack(side="left")

        # 2. Remote Distribution Settings
        up_card = ttk.LabelFrame(self.dtab_updates, text="Auto-Updater & Distribution Settings", padding=10)
        up_card.pack(fill="x", pady=6)

        u_grid = ttk.Frame(up_card)
        u_grid.pack(fill="x")

        ttk.Label(u_grid, text="GitHub Repository:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(u_grid, textvariable=self.repo_var, width=32).grid(row=0, column=1, sticky="w", padx=8, pady=2)
        ttk.Label(u_grid, text="(e.g. Rift/whatsapp-bulk-messenger)", font=("Segoe UI", 8), foreground="#666").grid(row=0, column=2, sticky="w")

        ttk.Label(u_grid, text="Release Branch:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(u_grid, textvariable=self.branch_var, width=15).grid(row=1, column=1, sticky="w", padx=8, pady=2)

        ttk.Label(u_grid, text="Custom URL / Cloudflare:").grid(row=2, column=0, sticky="w", pady=2)
        ttk.Entry(u_grid, textvariable=self.endpoint_var, width=32).grid(row=2, column=1, sticky="w", padx=8, pady=2)
        ttk.Label(u_grid, text="(Optional Cloudflare Worker or R2 bucket URL)", font=("Segoe UI", 8), foreground="#666").grid(row=2, column=2, sticky="w")

        ttk.Checkbutton(up_card, text="Check for updates automatically when application opens", variable=self.auto_check_var).pack(anchor="w", pady=4)

        u_btn_row = ttk.Frame(up_card)
        u_btn_row.pack(fill="x", pady=4)
        ttk.Button(u_btn_row, text="💾 Save Distribution Settings", command=self._save_update_channel_config).pack(side="left", padx=(0, 6))
        ttk.Button(u_btn_row, text="🔄 Check Remote Updates", style="Action.TButton", command=lambda: self._check_updates_gui(prompt_if_current=True)).pack(side="left")

        # 3. Developer Release Packager (Only for Developer)
        if self.device_info["is_developer"]:
            ship_card = ttk.LabelFrame(self.dtab_updates, text="📦 Developer 1-Click Release & Shipping Center", padding=10)
            ship_card.pack(fill="both", expand=True, pady=4)

            s_top = ttk.Frame(ship_card)
            s_top.pack(fill="x", pady=2)
            ttk.Label(s_top, text="Release Version:").pack(side="left", padx=(0, 4))
            ttk.Entry(s_top, textvariable=self.new_ver_var, width=10).pack(side="left", padx=(0, 12))
            ttk.Label(s_top, text="Changelog Highlights (one per line):").pack(side="left")

            self.changelog_text = tk.Text(ship_card, height=4, font=("Segoe UI", 9), wrap="word")
            self.changelog_text.pack(fill="x", pady=4)
            self.changelog_text.insert("1.0", "Performance and memory optimizations\nAdded anti-ban cooldown presets\nUpdated user contacts handling")

            s_acts = ttk.Frame(ship_card)
            s_acts.pack(fill="x", pady=4)
            ttk.Button(s_acts, text="📦 Build & Package Release (.zip)", style="BigAction.TButton", command=self._package_release_gui).pack(side="left", padx=(0, 8))
            ttk.Button(s_acts, text="📂 Open Releases Folder (dist/)", command=self._open_dist_folder).pack(side="left")
        else:
            client_card = ttk.LabelFrame(self.dtab_updates, text="📦 Release Publishing", padding=10)
            client_card.pack(fill="x", pady=4)
            ttk.Label(client_card, text="🔒 Release packaging is restricted to authorized developer hardware.", foreground="#777").pack(anchor="w")

    def _copy_device_id(self, full: bool = False):
        val = self.device_info["device_id"] if full else self.device_info["short_id"]
        self.clipboard_clear()
        self.clipboard_append(val)
        if hasattr(self, "btn_copy_id"):
            self.btn_copy_id.config(text="✓ Copied!")
            self.after(2000, lambda: self.btn_copy_id.config(text="📋 Copy"))

    def _open_audit_log(self):
        log_p = os.path.join(self.base_dir, "device_audit.log")
        if os.path.isfile(log_p):
            try:
                os.system(f'notepad.exe "{log_p}"')
            except Exception:
                pass
        else:
            messagebox.showinfo("Audit Log", "No audit log file created yet.")

    def _open_dist_folder(self):
        dist_p = os.path.join(self.base_dir, "dist")
        os.makedirs(dist_p, exist_ok=True)
        try:
            os.system(f'explorer "{dist_p}"')
        except Exception:
            pass

    def _save_update_channel_config(self):
        cfg = {
            "provider": "github",
            "github_repo": self.repo_var.get().strip(),
            "branch": self.branch_var.get().strip(),
            "custom_endpoint": self.endpoint_var.get().strip(),
            "auto_check_on_startup": self.auto_check_var.get()
        }
        Updater.save_update_config(cfg)
        messagebox.showinfo("Saved", "Update settings saved successfully.")

    def _check_updates_gui(self, prompt_if_current: bool = True):
        if self.is_checking_update:
            return
        self.is_checking_update = True
        if hasattr(self, "btn_check_update"):
            self.btn_check_update.config(text="Checking...", state="disabled")

        def worker():
            has_up, manifest, msg = Updater.check_for_updates(timeout=7)
            def on_done():
                self.is_checking_update = False
                if hasattr(self, "btn_check_update"):
                    self.btn_check_update.config(text="🔄 Check for Updates", state="normal")

                if has_up:
                    self.update_header_lbl.config(text=f"Update v{manifest.get('version')} available!", foreground="#e65100")
                    cl_list = manifest.get("changelog", [])
                    cl_text = "\n".join(f"• {c}" for c in cl_list)
                    ans = messagebox.askyesno(
                        "Update Available",
                        f"A new version v{manifest.get('version')} is available!\n\n"
                        f"Changelog:\n{cl_text}\n\n"
                        f"Would you like to download and install this update now?"
                    )
                    if ans:
                        self._start_update_download(manifest.get("download_url"))
                else:
                    if "up to date" in msg.lower():
                        self.update_header_lbl.config(text="Up to date ✓", foreground="#128C7E")
                        if prompt_if_current:
                            messagebox.showinfo("Up to Date", f"You are running the latest version (v{self.app_version}).")
                    else:
                        self.update_header_lbl.config(text="Offline / unreachable", foreground="#777")
                        if prompt_if_current:
                            messagebox.showwarning("Update Check", f"Could not check for updates:\n{msg}")

            self.after(0, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _start_update_download(self, download_url: str):
        if not download_url:
            messagebox.showerror("Error", "No download URL provided in release manifest.")
            return

        self.status_lbl.config(text="Downloading and applying update...")

        def worker():
            ok, msg = Updater.download_and_apply_update(
                download_url,
                progress_callback=lambda m: self.after(0, lambda: self.status_lbl.config(text=m))
            )
            def on_done():
                if ok:
                    messagebox.showinfo("Update Complete", msg)
                else:
                    messagebox.showerror("Update Error", msg)
            self.after(0, on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _package_release_gui(self):
        ver = self.new_ver_var.get().strip()
        if not ver:
            messagebox.showwarning("Missing Version", "Please enter a version number (e.g. 1.2.1).")
            return

        raw_cl = self.changelog_text.get("1.0", "end-1c").strip()
        cl_items = [line.strip().lstrip("•-* ") for line in raw_cl.split("\n") if line.strip()]

        ok, manifest, msg = Updater.package_release(ver, cl_items)
        if ok:
            messagebox.showinfo("Release Packaged", msg)
            self.app_version = ver
        else:
            messagebox.showerror("Packaging Failed", msg)

    # =========================================================================
    # 3. BOTTOM CONTROLS & DISPATCH ENGINE
    # =========================================================================
    def _build_bottom_controls(self):
        control_frame = ttk.Frame(self, padding="15 5 15 12")
        control_frame.pack(fill="x", side="bottom")

        btn_row = ttk.Frame(control_frame)
        btn_row.pack(fill="x", pady=4)

        self.btn_start = ttk.Button(btn_row, text="🚀 Start Sending Messages", style="BigAction.TButton", command=self.start_dispatch)
        self.btn_start.pack(side="left", padx=(0, 8))

        self.btn_pause = ttk.Button(btn_row, text="⏸ Pause", command=self.pause_dispatch, state="disabled")
        self.btn_pause.pack(side="left", padx=4)

        self.btn_stop = ttk.Button(btn_row, text="⏹ Stop", command=self.stop_dispatch, state="disabled")
        self.btn_stop.pack(side="left", padx=4)

        self.btn_export = ttk.Button(btn_row, text="📊 Export Report", command=self.export_report)
        self.btn_export.pack(side="right")

        self.progress_bar = ttk.Progressbar(control_frame, variable=self.prog_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=4)

        self.status_lbl = ttk.Label(control_frame, text="Ready. Choose contacts file and click Start Sending.", font=("Segoe UI", 9))
        self.status_lbl.pack(anchor="w")

    def _sync_simple_to_dev(self):
        txt = self.simple_msg_text.get("1.0", "end-1c")
        self.dev_msg_text.delete("1.0", tk.END)
        self.dev_msg_text.insert("1.0", txt)

    def _sync_dev_to_simple(self):
        txt = self.dev_msg_text.get("1.0", "end-1c")
        self.simple_msg_text.delete("1.0", tk.END)
        self.simple_msg_text.insert("1.0", txt)

    def _get_active_message(self) -> str:
        if self.dev_mode_var.get():
            return self.dev_msg_text.get("1.0", "end-1c")
        return self.simple_msg_text.get("1.0", "end-1c")

    def _browse_contacts_file(self):
        f = filedialog.askopenfilename(
            initialdir=self.base_dir,
            title="Select Contacts File",
            filetypes=[("Excel or CSV Files", "*.xlsx;*.xls;*.csv"), ("Excel Files", "*.xlsx;*.xls"), ("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        if f:
            self.file_path_var.set(f)
            self._reload_contacts_data()

    def _browse_media_file(self):
        f = filedialog.askopenfilename(
            initialdir=self.base_dir,
            title="Select Picture, Video, or Document",
            filetypes=[("All Media & Docs", "*.png;*.jpg;*.jpeg;*.webp;*.mp4;*.mov;*.pdf;*.docx;*.zip"), ("Images", "*.png;*.jpg;*.jpeg;*.webp"), ("Videos", "*.mp4;*.mov"), ("Documents", "*.pdf;*.docx;*.zip"), ("All Files", "*.*")]
        )
        if f:
            self.attach_path_var.set(f)
            self.attach_enabled_var.set(True)
            size_mb = os.path.getsize(f) / (1024 * 1024)
            info = f"Attached: {os.path.basename(f)} ({size_mb:.2f} MB)"
            self.simple_media_status.config(text=info, foreground="#0066cc")
            self.simple_btn_remove_media.config(state="normal")

    def _reload_contacts_data(self):
        path = self.file_path_var.get().strip()
        if not path or not os.path.isfile(path):
            return

        try:
            contacts = DataLoader.load_contacts(
                file_path=path,
                default_message=self._get_active_message(),
                default_country_code=self.cc_var.get().strip()
            )
            self.loaded_contacts = contacts

            # Update Simple status
            self.simple_file_status.config(text=f"Selected: {os.path.basename(path)} ({len(contacts)} contacts ready to send)", foreground="#128C7E")

            # Update Dev Treeview
            for item in self.dev_tree.get_children():
                self.dev_tree.delete(item)
            for c in contacts:
                att = os.path.basename(c["attachment"]) if c["attachment"] else "-"
                self.dev_tree.insert("", "end", values=(c["phone"], c["name"], c["message"][:50] + "...", att))

            self.dev_contact_count_lbl.config(text=f"Total Loaded: {len(contacts)} contacts ready to dispatch")
        except Exception as e:
            messagebox.showerror("File Error", f"Could not read contacts:\n{e}")

    def start_dispatch(self):
        if self.is_running:
            return

        path = self.file_path_var.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("Missing File", "Please select an Excel or CSV contacts file first!")
            return

        self._reload_contacts_data()
        if not self.loaded_contacts:
            messagebox.showwarning("No Contacts", "No valid contacts found in the selected file!")
            return

        self._save_current_config()

        if self.sched_enabled_var.get():
            t_str = self.sched_time_var.get().strip()
            self.status_lbl.config(text=f"Scheduler active: Waiting for {t_str}...")
            self.btn_start.config(state="disabled")
            self.btn_stop.config(state="normal")
            self.is_running = True
            self.worker_thread = threading.Thread(target=self._scheduler_worker, daemon=True)
            self.worker_thread.start()
            return

        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_stop.config(state="normal")
        self.is_running = True

        self.worker_thread = threading.Thread(target=self._dispatch_worker, daemon=True)
        self.worker_thread.start()

    def pause_dispatch(self):
        if self.engine:
            if not self.engine._is_paused:
                self.engine.pause()
                self.btn_pause.config(text="▶ Resume")
                self.status_lbl.config(text="PAUSED. Click Resume to continue.")
            else:
                self.engine.resume()
                self.btn_pause.config(text="⏸ Pause")
                self.status_lbl.config(text="Resumed sending.")

    def stop_dispatch(self):
        if self.engine:
            self.engine.stop()
        self.is_running = False
        self.status_lbl.config(text="Stopped by user.")
        self.btn_start.config(state="normal")
        self.btn_pause.config(state="disabled", text="⏸ Pause")
        self.btn_stop.config(state="disabled")

    def _dispatch_worker(self):
        try:
            self.status_lbl.config(text="Opening browser for WhatsApp Web...")
            b_key = self.browser_var.get()
            p_idx = self.profile_combo.current() if hasattr(self, "profile_combo") else 0
            profile = self.current_profiles[p_idx] if p_idx >= 0 and p_idx < len(self.current_profiles) else self.current_profiles[0]
            headless = self.headless_var.get()

            driver = BrowserManager.launch_driver(b_key, profile, headless=headless)
            self.driver = driver
            self.engine = WhatsAppEngine(driver)

            self.status_lbl.config(text="Checking WhatsApp Web login...")
            if not self.engine.ensure_logged_in(timeout=90, status_callback=lambda m: self.status_lbl.config(text=m)):
                messagebox.showerror("Login Timeout", "WhatsApp Web login timed out. Please scan the QR code and try again.")
                return

            min_d = self.min_delay_var.get()
            max_d = self.max_delay_var.get()
            b_size = self.batch_size_var.get()
            b_pause = self.batch_pause_var.get()
            cap = self.daily_cap_var.get()
            global_att = self.attach_path_var.get().strip() if self.attach_enabled_var.get() else None

            def on_progress(idx, total, contact, record):
                pct = (idx / total) * 100
                self.prog_var.set(pct)
                st = record["status"]
                self.status_lbl.config(text=f"[{idx}/{total}] {contact['name']} (+{contact['phone']}): {st}")

            results = self.engine.send_batch(
                contacts=self.loaded_contacts,
                min_delay=min_d,
                max_delay=max_d,
                batch_size=b_size,
                batch_cooldown_secs=b_pause,
                max_daily_limit=cap,
                global_attachment=global_att,
                progress_callback=on_progress,
                log_callback=lambda m: self.status_lbl.config(text=m)
            )

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.last_report_path = os.path.join(self.base_dir, f"whatsapp_report_{timestamp}.csv")
            import csv
            with open(self.last_report_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["name", "phone", "status", "error", "attachment", "timestamp"])
                writer.writeheader()
                writer.writerows(results)

            sent = sum(1 for r in results if r["status"] == "SENT")
            inv = sum(1 for r in results if r["status"] == "INVALID_NUMBER")
            failed = sum(1 for r in results if r["status"] == "FAILED")

            self.status_lbl.config(text=f"Finished! Sent: {sent} | Invalid: {inv} | Failed: {failed}")
            messagebox.showinfo("Done!", f"Finished sending messages!\n\nSent: {sent}\nInvalid: {inv}\nFailed: {failed}\n\nReport saved to: {os.path.basename(self.last_report_path)}")

        except Exception as e:
            self.status_lbl.config(text=f"Error: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
            self.is_running = False
            self.btn_start.config(state="normal")
            self.btn_pause.config(state="disabled", text="⏸ Pause")
            self.btn_stop.config(state="disabled")

    def _scheduler_worker(self):
        t_str = self.sched_time_var.get().strip()
        try:
            shour, smin = map(int, t_str.split(":"))
        except ValueError:
            messagebox.showerror("Invalid Schedule", "Please use HH:MM format (e.g. 09:30).")
            self.stop_dispatch()
            return

        while self.is_running:
            now = datetime.datetime.now()
            target = now.replace(hour=shour, minute=smin, second=0, microsecond=0)
            if target <= now:
                target += datetime.timedelta(days=1)

            secs = (target - now).total_seconds()
            self.status_lbl.config(text=f"Scheduled: Next alarm at {target.strftime('%Y-%m-%d %H:%M:%S')} (in {secs/3600:.1f} hrs)")

            while secs > 0 and self.is_running:
                chunk = min(secs, 10)
                time.sleep(chunk)
                secs -= chunk

            if self.is_running:
                self.status_lbl.config(text="Alarm triggered! Starting dispatch...")
                self._dispatch_worker()

    def export_report(self):
        if hasattr(self, "last_report_path") and os.path.isfile(self.last_report_path):
            os.system(f'explorer /select,"{self.last_report_path}"')
        else:
            messagebox.showinfo("Report", "No dispatch report generated yet in this session.")

    def _save_current_config(self):
        cfg = {
            "browser": self.browser_var.get(),
            "profile_index": self.profile_combo.current() if hasattr(self, "profile_combo") else 0,
            "data_file": self.file_path_var.get(),
            "default_country_code": self.cc_var.get(),
            "default_message": self._get_active_message(),
            "min_delay": self.min_delay_var.get(),
            "max_delay": self.max_delay_var.get(),
            "batch_size": self.batch_size_var.get(),
            "batch_pause": self.batch_pause_var.get(),
            "daily_cap": self.daily_cap_var.get(),
            "attach_enabled": self.attach_enabled_var.get(),
            "attachment_path": self.attach_path_var.get(),
            "headless": self.headless_var.get(),
            "sched_enabled": self.sched_enabled_var.get(),
            "sched_time": self.sched_time_var.get(),
            "dev_mode": self.dev_mode_var.get()
        }
        try:
            with open(os.path.join(self.base_dir, CONFIG_FILE), "w", encoding="utf-8") as f:
                import json
                json.dump(cfg, f, indent=4)
        except Exception:
            pass

    def _load_saved_config(self):
        cfg_path = os.path.join(self.base_dir, CONFIG_FILE)
        sample_xlsx = os.path.join(self.base_dir, "contacts_sample.xlsx")

        if not os.path.isfile(cfg_path):
            if os.path.isfile(sample_xlsx):
                self.file_path_var.set(sample_xlsx)
                self._reload_contacts_data()
            return

        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                import json
                cfg = json.load(f)

            if "dev_mode" in cfg:
                self.dev_mode_var.set(cfg["dev_mode"])

            if "browser" in cfg and cfg["browser"] in self.installed_browsers:
                self.browser_var.set(cfg["browser"])
                self._refresh_profiles()

            if "profile_index" in cfg and hasattr(self, "profile_combo") and cfg["profile_index"] < len(self.current_profiles):
                self.profile_combo.current(cfg["profile_index"])

            target_f = cfg.get("data_file")
            if target_f and os.path.isfile(target_f):
                self.file_path_var.set(target_f)
                self._reload_contacts_data()
            elif os.path.isfile(sample_xlsx):
                self.file_path_var.set(sample_xlsx)
                self._reload_contacts_data()

            if "default_country_code" in cfg:
                self.cc_var.set(cfg["default_country_code"])

            if "default_message" in cfg and cfg["default_message"]:
                self.simple_msg_text.delete("1.0", tk.END)
                self.simple_msg_text.insert("1.0", cfg["default_message"])
                self.dev_msg_text.delete("1.0", tk.END)
                self.dev_msg_text.insert("1.0", cfg["default_message"])

            if "min_delay" in cfg:
                self.min_delay_var.set(cfg["min_delay"])
            if "max_delay" in cfg:
                self.max_delay_var.set(cfg["max_delay"])
            if "batch_size" in cfg:
                self.batch_size_var.set(cfg["batch_size"])
            if "batch_pause" in cfg:
                self.batch_pause_var.set(cfg["batch_pause"])
            if "daily_cap" in cfg:
                self.daily_cap_var.set(cfg["daily_cap"])

            if "attach_enabled" in cfg:
                self.attach_enabled_var.set(cfg["attach_enabled"])
            if "attachment_path" in cfg and os.path.isfile(cfg["attachment_path"]):
                self.attach_path_var.set(cfg["attachment_path"])
                size_mb = os.path.getsize(cfg["attachment_path"]) / (1024 * 1024)
                info = f"Attached: {os.path.basename(cfg['attachment_path'])} ({size_mb:.2f} MB)"
                self.simple_media_status.config(text=info, foreground="#0066cc")
                self.simple_btn_remove_media.config(state="normal")

            if "headless" in cfg:
                self.headless_var.set(cfg["headless"])
            if "sched_enabled" in cfg:
                self.sched_enabled_var.set(cfg["sched_enabled"])
            if "sched_time" in cfg:
                self.sched_time_var.set(cfg["sched_time"])

        except Exception as e:
            print(f"[INFO] Could not load saved config: {e}")


def launch_gui():
    app = WhatsAppGUI()
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
