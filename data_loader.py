"""
Data Loader for WhatsApp Bulk Automation
Supports Excel (.xlsx, .xls) and CSV (.csv) files.
Handles flexible column names, phone number sanitization, message templating, and media attachment detection.
"""

import os
import csv
import re
from typing import List, Dict, Optional, Tuple


class DataLoader:
    PHONE_SYNONYMS = ["phone", "contact", "mobile", "number", "phone number", "contact number", "mobile number", "cell"]
    NAME_SYNONYMS = ["name", "customer_name", "customer", "client", "recipient", "person", "full name"]
    MESSAGE_SYNONYMS = ["message", "msg", "text", "body", "content", "custom_message"]
    ATTACHMENT_SYNONYMS = ["attachment", "media", "file", "image", "document", "pdf", "video", "filepath"]

    @classmethod
    def list_available_data_files(cls, directory: str) -> List[str]:
        """Scans the directory for suitable Excel and CSV files."""
        valid_extensions = (".xlsx", ".xls", ".csv")
        files = []
        for f in os.listdir(directory):
            if f.lower().endswith(valid_extensions) and not f.startswith("~$") and not f.startswith("whatsapp_report_"):
                files.append(f)
        return files

    @classmethod
    def create_sample_files_if_needed(cls, directory: str):
        """Creates sample Excel and CSV template files with attachment column support."""
        csv_path = os.path.join(directory, "contacts_sample.csv")
        xlsx_path = os.path.join(directory, "contacts_sample.xlsx")

        headers = ["Phone", "Name", "Message", "Attachment"]
        sample_rows = [
            ["+919876543210", "Alex Mercer", "{Hi|Hello|Hey} {name}, thank you for connecting with us! Here is your custom update.", ""],
            ["+14155552671", "Sarah Connor", "{Greetings|Hello} {name}, your scheduled notification is ready.", ""],
        ]

        if not os.path.exists(csv_path):
            try:
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    writer.writerows(sample_rows)
            except Exception as e:
                print(f"[INFO] Could not create CSV sample: {e}")

        if not os.path.exists(xlsx_path):
            try:
                import openpyxl
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Contacts"
                ws.append(headers)
                for row in sample_rows:
                    ws.append(row)
                wb.save(xlsx_path)
            except Exception as e:
                print(f"[INFO] Could not create Excel sample: {e}")

    @classmethod
    def load_contacts(cls, file_path: str, default_message: str = "", default_country_code: str = "") -> List[Dict[str, str]]:
        """
        Loads contacts from an Excel (.xlsx/.xls) or CSV file.
        Returns a list of dicts: [{'phone': '...', 'name': '...', 'message': '...', 'attachment': '...', 'raw_phone': '...'}]
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Data file not found at: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".csv":
            raw_data = cls._read_csv(file_path)
        elif ext in (".xlsx", ".xls"):
            raw_data = cls._read_excel(file_path)
        else:
            raise ValueError(f"Unsupported file format '{ext}'. Please provide a .xlsx, .xls, or .csv file.")

        if not raw_data:
            return []

        headers = list(raw_data[0].keys())
        phone_key = cls._match_header(headers, cls.PHONE_SYNONYMS)
        name_key = cls._match_header(headers, cls.NAME_SYNONYMS)
        message_key = cls._match_header(headers, cls.MESSAGE_SYNONYMS)
        attachment_key = cls._match_header(headers, cls.ATTACHMENT_SYNONYMS)

        if not phone_key:
            raise ValueError(
                f"Could not find a phone number column in {file_path}.\n"
                f"Found columns: {headers}\n"
                f"Expected one of: {cls.PHONE_SYNONYMS}"
            )

        base_dir = os.path.dirname(os.path.abspath(file_path))
        contacts = []

        for row in raw_data:
            raw_phone = str(row.get(phone_key, "") or "").strip()
            phone = cls.clean_phone_number(raw_phone, default_country_code)

            if not phone:
                continue

            name = str(row.get(name_key, "") or "").strip() if name_key else "Customer"
            row_msg = str(row.get(message_key, "") or "").strip() if message_key else ""
            template = row_msg if row_msg else default_message

            # Variable substitution
            first_name = name.split()[0] if name else "there"
            formatted_msg = template.replace("{name}", name)
            formatted_msg = formatted_msg.replace("{customer_name}", name)
            formatted_msg = formatted_msg.replace("{first_name}", first_name)
            formatted_msg = formatted_msg.replace("{phone}", phone)

            for k, v in row.items():
                if k and v:
                    formatted_msg = formatted_msg.replace(f"{{{k.lower()}}}", str(v))

            # Attachment file resolution
            attachment_file = None
            if attachment_key:
                raw_attach = str(row.get(attachment_key, "") or "").strip()
                if raw_attach:
                    if os.path.isabs(raw_attach) and os.path.isfile(raw_attach):
                        attachment_file = raw_attach
                    else:
                        rel_path = os.path.join(base_dir, raw_attach)
                        if os.path.isfile(rel_path):
                            attachment_file = rel_path

            contacts.append({
                "phone": phone,
                "name": name,
                "message": formatted_msg,
                "attachment": attachment_file,
                "raw_phone": raw_phone
            })

        return contacts

    @staticmethod
    def _match_header(headers: List[str], synonyms: List[str]) -> Optional[str]:
        for h in headers:
            normalized = h.strip().lower().replace("_", " ")
            if normalized in synonyms:
                return h
        for h in headers:
            normalized = h.strip().lower()
            for syn in synonyms:
                if syn in normalized:
                    return h
        return None

    @staticmethod
    def clean_phone_number(raw_phone: str, default_country_code: str = "") -> Optional[str]:
        """Cleans and validates phone numbers for WhatsApp URL scheme."""
        digits = re.sub(r"[^\d]", "", raw_phone)
        if not digits:
            return None

        # If 10 digits and default country code is provided
        if len(digits) == 10 and default_country_code:
            clean_cc = re.sub(r"[^\d]", "", default_country_code)
            digits = clean_cc + digits

        if len(digits) < 10 or len(digits) > 16:
            return None

        return digits

    @staticmethod
    def _read_csv(file_path: str) -> List[Dict[str, str]]:
        rows = []
        with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if any(r.values()):
                    rows.append(r)
        return rows

    @staticmethod
    def _read_excel(file_path: str) -> List[Dict[str, str]]:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet = wb.active

        rows_iter = sheet.iter_rows(values_only=True)
        try:
            raw_headers = next(rows_iter)
        except StopIteration:
            return []

        headers = [str(h).strip() if h is not None else f"col_{idx}" for idx, h in enumerate(raw_headers)]

        data = []
        for row in rows_iter:
            if not row or not any(row):
                continue
            row_dict = {}
            for idx, val in enumerate(row):
                if idx < len(headers):
                    row_dict[headers[idx]] = str(val).strip() if val is not None else ""
            data.append(row_dict)

        return data
