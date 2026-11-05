"""
WhatsApp Automated Bulk Sender
Launches the Desktop GUI by default, or runs in headless/CLI mode when requested.
Includes device auditing, developer role detection, auto-updater hooks, pre-flight validation,
and dry-run simulation capabilities.
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
from config_manager import ConfigManager, AppConfig, BUILTIN_PRESETS
from validator import PreFlightValidator, DryRunEngine
from logger import get_logger, mask_phone

logger = get_logger("Runner")

CONFIG_FILE = "config.json"


def load_config() -> dict:
    """Loads application configuration as a dictionary for backward compatibility."""
    return ConfigManager.load().to_dict()


def save_config(cfg: dict):
    """Saves dictionary configuration through the validated ConfigManager."""
    app_cfg = AppConfig.from_dict(cfg)
    ConfigManager.save(app_cfg)


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


def run_batch_job(cfg: dict, headless: bool = False, dry_run: bool = False, dedupe: bool = False):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    app_cfg = AppConfig.from_dict(cfg)
    data_path = app_cfg.data_file
    if not os.path.isabs(data_path):
        data_path = os.path.join(base_dir, data_path)

    print("\n" + "=" * 60)
    print("STARTING WHATSAPP BULK DISPATCH (CLI / AUTOMATED MODE)")
    print(f"Browser   : {app_cfg.browser.title()}")
    print(f"Profile   : {cfg.get('profile', {}).get('name', 'Dedicated Profile')}")
    print(f"Data File : {os.path.basename(data_path)}")
    print(f"Preset    : {app_cfg.active_preset.title()}")
    print("=" * 60)

    try:
        contacts = DataLoader.load_contacts(
            file_path=data_path,
            default_message=app_cfg.default_message,
            default_country_code=app_cfg.default_country_code
        )
    except Exception as e:
        logger.error(f"Failed to load contacts: {e}")
        print(f"[ERROR] Failed to load contacts: {e}")
        return

    if not contacts:
        logger.warning("No valid contacts found in file.")
        print("[WARNING] No valid contacts found in file.")
        return

    # Pre-Flight Validation Audit
    report = PreFlightValidator.audit_contacts(contacts, app_cfg)
    print("\n" + report.summary())

    if dedupe and report.duplicate_count > 0:
        contacts, removed = PreFlightValidator.deduplicate_contacts(contacts)
        print(f"[INFO] Automatically removed {removed} duplicate contacts.")

    # Dry-Run Mode Simulation
    if dry_run:
        print("\n" + "=" * 60)
        print("EXECUTING DRY-RUN SIMULATION (NO BROWSER OR NETWORK CALLS)")
        print("=" * 60)
        sim = DryRunEngine.simulate_campaign(contacts, app_cfg, sample_size=5)
        print(f"Total Targets    : {sim['total_recipients']}")
        print(f"Estimated Time   : ~{sim['estimated_duration_minutes']:.1f} minutes")
        print("\nSample Generated Messages:")
        for sm in sim["sample_messages"]:
            print(f"  [{sm['index']}] {sm['name']} (+{sm['phone_masked']}):")
            print(f"      \"{sm['simulated_message']}\"")
            if sm["attachment"]:
                print(f"      Attachment: {os.path.basename(sm['attachment'])}")
        print("\n[OK] Dry-run simulation completed successfully.")
        return

    if not report.is_ready_to_send:
        print("[ERROR] Contact list is not ready for dispatch. Please resolve errors listed above.")
        return

    print(f"[OK] Ready to dispatch to {min(len(contacts), app_cfg.daily_cap)} contacts.")

    driver = None
    try:
        driver = BrowserManager.launch_driver(
            browser_key=app_cfg.browser,
            profile=cfg.get("profile", {
                "dir": "__dedicated__",
                "name": "Dedicated",
                "path": os.path.join(base_dir, "whatsapp_browser_session"),
                "is_dedicated": True
            }),
            headless=headless
        )
    except Exception as e:
        logger.error(f"Could not start browser driver: {e}")
        print(f"\n[ERROR] Could not start browser driver: {e}")
        return

    try:
        engine = WhatsAppEngine(driver)
        if not engine.ensure_logged_in(timeout=90):
            print("[ERROR] Login verification failed. Aborting.")
            return

        global_att = app_cfg.attachment_path if app_cfg.attach_enabled else None

        results = engine.send_batch(
            contacts=contacts,
            min_delay=app_cfg.min_delay,
            max_delay=app_cfg.max_delay,
            batch_size=app_cfg.batch_size,
            batch_cooldown_secs=app_cfg.batch_pause,
            max_daily_limit=app_cfg.daily_cap,
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
            logger.warning(f"Could not write report file: {e}")
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
            logger.error(f"Scheduler batch job failed: {e}")
            print(f"[SCHEDULER ERROR] Batch job failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="WhatsApp Automated Bulk Sender")
    parser.add_argument("--cli", action="store_true", help="Run in CLI mode without opening GUI")
    parser.add_argument("--auto", action="store_true", help="Run automatically using saved config")
    parser.add_argument("--schedule", type=str, default=None, help="Schedule daily execution at HH:MM (e.g. 09:30)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (background)")
    parser.add_argument("--file", type=str, default=None, help="Override contacts file path")
    parser.add_argument("--preset", type=str, default=None, choices=["safe", "balanced", "fast"], help="Apply safety preset (safe, balanced, fast)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate campaign without opening browser or sending messages")
    parser.add_argument("--validate", action="store_true", help="Perform pre-flight validation audit on contacts file")
    parser.add_argument("--dedupe", action="store_true", help="Automatically remove duplicate phone numbers")
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

    # If --validate is passed, perform standalone pre-flight audit
    if args.validate:
        print_banner()
        cfg = load_config()
        app_cfg = AppConfig.from_dict(cfg)
        target_f = args.file or app_cfg.data_file
        if not os.path.isabs(target_f):
            target_f = os.path.join(base_dir, target_f)
        print(f"\nAuditing contacts file: {os.path.basename(target_f)}...")
        try:
            contacts = DataLoader.load_contacts(target_f, default_country_code=app_cfg.default_country_code)
            report = PreFlightValidator.audit_contacts(contacts, app_cfg)
            print(report.summary())
        except Exception as e:
            print(f"[ERROR] Could not audit contacts: {e}")
        return

    # If no CLI arguments provided, launch the GUI interface!
    if not (args.cli or args.auto or args.schedule or args.dry_run):
        try:
            from gui import launch_gui
            launch_gui()
            return
        except Exception as e:
            logger.warning(f"Could not launch GUI ({e}). Falling back to CLI mode.")
            print(f"[WARNING] Could not launch GUI ({e}). Falling back to CLI mode.")

    # CLI / Automated mode
    print_banner()
    cfg = load_config()
    app_cfg = AppConfig.from_dict(cfg)

    if args.preset:
        app_cfg.apply_preset(args.preset)
        cfg = app_cfg.to_dict()

    if args.file:
        cfg["data_file"] = args.file

    if args.schedule:
        run_scheduler_loop(cfg, args.schedule, headless=args.headless)
    else:
        run_batch_job(cfg, headless=args.headless, dry_run=args.dry_run, dedupe=args.dedupe)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Script stopped by user (Ctrl+C). Exiting.")
        sys.exit(0)
