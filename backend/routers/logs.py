"""
Audit Logs and System Telemetry API Router.
Provides endpoints for retrieving filtered application audit logs and KPI metrics.
"""

import io
import csv
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from backend.database import db

router = APIRouter(prefix="/api/logs", tags=["Logs"])


@router.get("/export")
def export_audit_logs_csv():
    """Generates and downloads a complete CSV audit log of all system and message dispatch events."""
    logs = db.get_audit_logs(level="ALL", limit=5000, offset=0)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Level", "Module", "Message"])
    for entry in logs:
        writer.writerow([
            entry.get("timestamp", ""),
            entry.get("level", ""),
            entry.get("module", ""),
            entry.get("message", "")
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=whatsapp_activity_audit_log.csv"}
    )


@router.get("")
def get_audit_logs(
    level: Optional[str] = Query("ALL", description="Filter by level: ALL, INFO, WARNING, ERROR"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Retrieves paginated audit log entries."""
    logs = db.get_audit_logs(level=level, limit=limit, offset=offset)
    return {
        "logs": logs,
        "count": len(logs),
        "limit": limit,
        "offset": offset
    }


@router.get("/kpis")
def get_dashboard_kpis():
    """Returns overview statistics: contacts, templates, jobs, delivery rate."""
    return db.get_overview_kpis()

