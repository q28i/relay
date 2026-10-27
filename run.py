"""
WhatsApp Automated Bulk Sender
Launches the Desktop GUI by default, or runs in headless/CLI mode when requested.
Includes device auditing, developer role detection, and auto-updater hooks.
"""

import os
import sys
import json
import time
import argparse
import datetime

from browser_manager import BrowserManager
from data_loader import DataLoader
from whatsapp_engine import WhatsAppEngine
from device_manager import DeviceManager
from updater import Updater

CONFIG_FILE = "config.json"


def load_config() -> dict:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(base_dir, CONFIG_FILE)
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(cfg: dict):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(base_dir, CONFIG_FILE)
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
    except Exception as e:
        print(f"[WARNING] Could not save config.json: {e}")


# Set UTF-8 encoding on Windows console if possible
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def print_banner():
    version = Updater.get_current_version()
    dev_info = DeviceManager.get_device_info()
    role_badge = "[DEVELOPER]" if dev_info["is_developer"] else "[CLIENT]"

    print("=" * 64)
    print(f"       WhatsApp Bulk Messenger Pro - v{version}")
    print(f"       Device ID : {dev_info['short_id']} {role_badge}")
    print(f"       Machine   : {dev_info['machine_name']} | OS: {dev_info['os']}")
    print("=" * 64)


def run_batch_job(cfg: dict, headless: bool = False):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = cfg.get("data_file", "")
    if not os.path.isabs(data_path):
        data_path = os.path.join(base_dir, data_path)

    print("\n" + "=" * 60)
    print("STARTING WHATSAPP BULK DISPATCH (CLI / AUTOMATED MODE)")
    print(f"Browser   : {cfg.get('browser', 'chrome').title()}")
    print(f"Profile   : {cfg.get('profile', {}).get('name', 'Default')}")
    print(f"Data File : {os.path.basename(data_path)}")
    print("=" * 60)

    try:
        contacts = DataLoader.load_contacts(
            file_path=data_path,
            default_message=cfg.get("default_message", "Hello {name}"),
            default_country_code=cfg.get("default_country_code", "")
        )
    except Exception as e:
        print(f"[ERROR] Failed to load contacts: {e}")
        return

    if not contacts:
        print("[WARNING] No valid contacts found in file.")
        return

    print(f"[OK] Successfully loaded {len(contacts)} contacts from {os.path.basename(data_path)}.")

    driver = None
    try:
        driver = BrowserManager.launch_driver(
            browser_key=cfg.get("browser", "chrome"),
            profile=cfg.get("profile", {"dir": "__dedicated__", "name": "Dedicated", "path": os.path.join(base_dir, "whatsapp_browser_session"), "is_dedicated": True}),
            headless=headless
        )
    except Exception as e:
        print(f"\n[ERROR] Could not start browser driver: {e}")
        return

    try:
        engine = WhatsAppEngine(driver)
        if not engine.ensure_logged_in(timeout=90):
            print("[ERROR] Login verification failed. Aborting.")
            return

        min_d = float(cfg.get("min_delay", 8.0))
        max_d = float(cfg.get("max_delay", 15.0))
        b_size = int(cfg.get("batch_size", 20))
        b_pause = float(cfg.get("batch_pause", 60.0))
        cap = int(cfg.get("daily_cap", 100))
        global_att = cfg.get("attachment_path") if cfg.get("attach_enabled") else None

        results = engine.send_batch(
            contacts=contacts,
            min_delay=min_d,
            max_delay=max_d,
            batch_size=b_size,
            batch_cooldown_secs=b_pause,
            max_daily_limit=cap,
            global_attachment=global_att
        )

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = os.path.join(base_dir, f"whatsapp_report_{timestamp}.csv")
        try:
            import csv
            with open(report_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["name", "phone", "status", "error", "attachment", "timestamp"])
                writer.writeheader()
                writer.writerows(results)
            print(f"\n[REPORT] Detailed delivery report saved to: {os.path.basename(report_file)}")
        except Exception as e:
            print(f"[WARNING] Could not write report file: {e}")

        sent_cnt = sum(1 for r in results if r["status"] == "SENT")
        invalid_cnt = sum(1 for r in results if r["status"] == "INVALID_NUMBER")
        fail_cnt = sum(1 for r in results if r["status"] == "FAILED")

        print("\n" + "=" * 60)
        print("DISPATCH SUMMARY")
        print(f"Total Contacts    : {len(contacts)}")
        print(f"Successfully Sent : {sent_cnt}")
        print(f"Invalid Numbers   : {invalid_cnt}")
        print(f"Failed            : {fail_cnt}")
        print("=" * 60)

    finally:
        if driver:
            print("[INFO] Closing browser session.")
            try:
                driver.quit()
            except Exception:
                pass


def run_scheduler_loop(cfg: dict, schedule_time_str: str, headless: bool = False):
    try:
        sched_hour, sched_min = map(int, schedule_time_str.split(":"))
    except ValueError:
        print(f"[ERROR] Invalid schedule format '{schedule_time_str}'. Expected HH:MM (e.g. 09:30).")
        return

    print("\n" + "=" * 60)
    print(f"WHATSAPP DAILY SCHEDULER ACTIVE - Trigger Time: {schedule_time_str}")
    print("=" * 60)

    while True:
        now = datetime.datetime.now()
        target = now.replace(hour=sched_hour, minute=sched_min, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)

        seconds_until = (target - now).total_seconds()
        print(f"\n[SCHEDULER] Next run at: {target.strftime('%Y-%m-%d %H:%M:%S')} (in {seconds_until / 3600:.2f} hours)")

        time.sleep(seconds_until)

        print(f"\n[SCHEDULER] Alarm triggered! Executing batch job...")
        try:
            run_batch_job(cfg, headless=headless)
        except Exception as e:
            print(f"[SCHEDULER ERROR] Batch job failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="WhatsApp Automated Bulk Sender")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode without opening GUI")
    parser.add_argument("--auto", action="store_true", help="Run automatically using saved config")
    parser.add_argument("--schedule", type=str, default=None, help="Schedule daily execution at HH:MM (e.g. 09:30)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (background)")
    parser.add_argument("--file", type=str, default=None, help="Override contacts file path")
    parser.add_argument("--device-info", action="store_true", help="Display hardware Device ID and role")
    parser.add_argument("--check-update", action="store_true", help="Check remote repository for updates")
    parser.add_argument("--package-release", type=str, default=None, metavar="VERSION", help="Package a release zip (Developer only)")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    DataLoader.create_sample_files_if_needed(base_dir)

    # 1. Device Auditing & Configuration Logging
    app_ver = Updater.get_current_version()
    DeviceManager.log_device_startup(app_ver)
    DeviceManager.save_auth_config()

    if args.device_info:
        print_banner()
        info = DeviceManager.get_device_info()
        print("\nFull Device Details:")
        for k, v in info.items():
            print(f"  {k:16}: {v}")
        return

    if args.check_update:
        print_banner()
        print("\nChecking for updates...")
        has_up, manifest, msg = Updater.check_for_updates()
        print(f"Status: {msg}")
        if has_up:
            print(f"New Version : v{manifest.get('version')}")
            print(f"Released    : {manifest.get('release_date')}")
            print(f"Download URL: {manifest.get('download_url')}")
            print("Changelog:")
            for item in manifest.get("changelog", []):
                print(f"  • {item}")
        return

    if args.package_release:
        print_banner()
        new_v = args.package_release
        print(f"\nPackaging release package for v{new_v}...")
        ok, manifest, msg = Updater.package_release(new_v, ["Production release update."])
        print(msg)
        return

    # If no CLI arguments provided, launch the GUI interface!
    if not (args.cli or args.auto or args.schedule):
        try:
            from gui import launch_gui
            launch_gui()
            return
        except Exception as e:
            print(f"[WARNING] Could not launch GUI ({e}). Falling back to CLI mode.")

    # CLI / Automated mode
    print_banner()
    cfg = load_config()
    if not cfg:
        print("[ERROR] No config.json found. Please run the GUI first or provide full configuration.")
        return

    if args.file:
        cfg["data_file"] = args.file

    if args.schedule:
        run_scheduler_loop(cfg, args.schedule, headless=args.headless)
    else:
        run_batch_job(cfg, headless=args.headless)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Script stopped by user (Ctrl+C). Exiting.")
        sys.exit(0)
