"""
Pre-Flight Validation, Deduplication, and Dry-Run Simulation Engine.
Audits contact lists for duplicate numbers, missing country codes, empty fields,
calculates campaign duration estimates, and generates explainable recommendations.
Includes DryRunEngine to simulate campaigns safely without launching browser instances.
"""

import os
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional

from config_manager import AppConfig
from whatsapp_engine import process_spintax
from logger import get_logger, mask_phone

logger = get_logger("PreFlightValidator")


@dataclass
class ValidationReport:
    """Diagnostic report summarizing contact list readiness and safety recommendations."""
    total_contacts: int = 0
    valid_contacts: int = 0
    duplicate_count: int = 0
    duplicates: List[Dict[str, Any]] = field(default_factory=list)
    invalid_phone_count: int = 0
    invalid_phones: List[Dict[str, Any]] = field(default_factory=list)
    missing_name_count: int = 0
    empty_message_count: int = 0
    attachment_issues: List[str] = field(default_factory=list)
    estimated_duration_minutes: float = 0.0
    recommendations: List[str] = field(default_factory=list)
    is_ready_to_send: bool = True

    def summary(self) -> str:
        """Returns a human-readable summary of the validation report."""
        lines = [
            "=" * 60,
            " PRE-FLIGHT VALIDATION & CAMPAIGN AUDIT REPORT",
            "=" * 60,
            f"Total Records Loaded      : {self.total_contacts}",
            f"Valid Recipients          : {self.valid_contacts}",
            f"Duplicate Numbers Found   : {self.duplicate_count}",
            f"Invalid Phone Numbers     : {self.invalid_phone_count}",
            f"Missing Recipient Names   : {self.missing_name_count}",
            f"Empty Message Bodies      : {self.empty_message_count}",
            f"Estimated Campaign Time   : ~{self.estimated_duration_minutes:.1f} minutes",
            "-" * 60,
        ]

        if self.recommendations:
            lines.append("RECOMMENDATIONS & OBSERVATIONS:")
            for rec in self.recommendations:
                lines.append(f"  • {rec}")
        else:
            lines.append("Status: All checks passed. Contact list is clean and ready.")

        lines.append("=" * 60)
        return "\n".join(lines)


class PreFlightValidator:
    """Performs deterministic sanity checks on contact lists before browser dispatch."""

    @classmethod
    def audit_contacts(cls, contacts: List[Dict[str, str]], config: AppConfig) -> ValidationReport:
        report = ValidationReport(total_contacts=len(contacts))
        if not contacts:
            report.is_ready_to_send = False
            report.recommendations.append("No contacts loaded. Please select a valid Excel or CSV file.")
            return report

        seen_phones = {}
        valid_count = 0

        for idx, c in enumerate(contacts, 1):
            phone = str(c.get("phone", "")).strip()
            name = str(c.get("name", "")).strip()
            msg = str(c.get("message", "")).strip()
            attach = c.get("attachment")

            # 1. Phone validation
            if not phone or len(phone) < 10 or len(phone) > 16 or not phone.isdigit():
                report.invalid_phone_count += 1
                report.invalid_phones.append({
                    "row": idx,
                    "raw_phone": c.get("raw_phone", phone),
                    "reason": "Must be 10-16 international digits"
                })
            else:
                valid_count += 1
                # Duplicate tracking
                if phone in seen_phones:
                    seen_phones[phone].append(idx)
                else:
                    seen_phones[phone] = [idx]

            # 2. Name check
            if not name or name.lower() in ("customer", "there", "friend"):
                report.missing_name_count += 1

            # 3. Message check
            if not msg:
                report.empty_message_count += 1

            # 4. Attachment check
            if attach and not os.path.isfile(attach):
                report.attachment_issues.append(f"Row {idx} ({name}): Attachment missing at {attach}")

        report.valid_contacts = valid_count

        # Process duplicates
        for p, rows in seen_phones.items():
            if len(rows) > 1:
                report.duplicate_count += (len(rows) - 1)
                report.duplicates.append({
                    "phone": p,
                    "masked_phone": mask_phone(p),
                    "count": len(rows),
                    "rows": rows
                })

        # Calculate estimated campaign duration
        total_to_send = min(valid_count, config.daily_cap)
        avg_jitter = (config.min_delay + config.max_delay) / 2.0
        total_jitter_seconds = total_to_send * avg_jitter

        cooldown_pauses = 0
        if config.batch_size > 0 and total_to_send > config.batch_size:
            cooldown_pauses = math.floor(total_to_send / config.batch_size)
        total_cooldown_seconds = cooldown_pauses * config.batch_pause

        # Base network overhead per message (~3 seconds for page load and send animation)
        network_overhead_seconds = total_to_send * 3.0
        total_seconds = total_jitter_seconds + total_cooldown_seconds + network_overhead_seconds
        report.estimated_duration_minutes = round(total_seconds / 60.0, 1)

        # Generate explainable recommendations
        if report.duplicate_count > 0:
            report.recommendations.append(
                f"{report.duplicate_count} duplicate phone number entries detected. "
                "Recommendation: Enable deduplication before sending to prevent sending duplicate messages to the same customer."
            )

        if report.invalid_phone_count > 0:
            report.recommendations.append(
                f"{report.invalid_phone_count} phone numbers are invalid (<10 digits or non-digits). "
                "These rows will be skipped during dispatch."
            )

        if report.missing_name_count > 0:
            report.recommendations.append(
                f"{report.missing_name_count} contacts have missing or generic names. "
                "Template tag '{name}' will default to 'Customer'."
            )

        if report.attachment_issues:
            report.recommendations.append(
                f"{len(report.attachment_issues)} row attachments were not found on disk. Verify file paths."
            )

        if total_to_send > 100 and avg_jitter < 8.0:
            report.recommendations.append(
                "High velocity setting: Sending >100 messages with <8s delay increases ban risk on newer SIMs. "
                "Consider switching to the 'Balanced' or 'Safe Warm-up' preset."
            )

        report.is_ready_to_send = valid_count > 0
        return report

    @classmethod
    def deduplicate_contacts(cls, contacts: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], int]:
        """
        Deduplicates contacts list based on cleaned phone number, preserving original order.
        Returns: (deduplicated_contacts_list, number_of_removed_duplicates)
        """
        deduped = []
        seen = set()
        removed_count = 0

        for c in contacts:
            p = str(c.get("phone", "")).strip()
            if not p:
                deduped.append(c)
                continue
            if p in seen:
                removed_count += 1
                continue
            seen.add(p)
            deduped.append(c)

        logger.info(f"Deduplication complete: removed {removed_count} duplicates, {len(deduped)} contacts retained.")
        return deduped, removed_count


class DryRunEngine:
    """Simulates message generation and pacing without launching a real browser."""

    @classmethod
    def simulate_campaign(
        cls,
        contacts: List[Dict[str, str]],
        config: AppConfig,
        sample_size: int = 5
    ) -> Dict[str, Any]:
        """
        Generates simulated message payloads with Spintax variation and pacing timeline.
        Does NOT launch a browser or make network requests.
        """
        report = PreFlightValidator.audit_contacts(contacts, config)
        total_to_send = min(len(contacts), config.daily_cap)

        samples = []
        for idx, c in enumerate(contacts[:min(sample_size, total_to_send)], 1):
            raw_msg = c.get("message", config.default_message)
            varied_msg = process_spintax(raw_msg)
            samples.append({
                "index": idx,
                "name": c.get("name", "Customer"),
                "phone_masked": mask_phone(c.get("phone")),
                "simulated_message": varied_msg,
                "attachment": c.get("attachment") or (config.attachment_path if config.attach_enabled else None)
            })

        simulation = {
            "is_ready": report.is_ready_to_send,
            "total_recipients": total_to_send,
            "estimated_duration_minutes": report.estimated_duration_minutes,
            "preset_applied": config.active_preset,
            "sample_messages": samples,
            "report_summary": report.summary()
        }

        return simulation

