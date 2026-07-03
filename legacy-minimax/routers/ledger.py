"""PocketBiz Ledger router — submit materials, view extractions, manage items."""

import json, sys, uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel

TZ = timezone(timedelta(hours=8))

# Make aihub pipeline importable
AIHUB_LEDGER = Path("/Users/vicki/service/aiHub/docs/pocketbiz-ledger")
SCRIPTS_DIR = AIHUB_LEDGER / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from extract_pipeline import extract as run_extraction

router = APIRouter(prefix="/ledger", tags=["ledger"])

LEDGER_DATA = AIHUB_LEDGER / "data" / "extractions"
LEDGER_DATA.mkdir(parents=True, exist_ok=True)


class SubmitRequest(BaseModel):
    text: str
    source_channel: str = "web"
    type_hint: str = "auto"


class ConfirmRequest(BaseModel):
    inbox_item_id: str
    candidate_index: int = 0
    action: str = "confirm"  # confirm | reject | edit


@router.post("/extract")
async def ledger_extract(req: SubmitRequest):
    """Submit raw text for AI extraction. Returns structured candidate."""
    result = run_extraction(
        req.text,
        source_channel=req.source_channel,
        type_hint=req.type_hint,
    )
    inbox_item_id = result.get("inbox_item_id", uuid.uuid4().hex[:12])
    result["inbox_item_id"] = inbox_item_id
    result["created_at"] = datetime.now(TZ).isoformat()
    result["status"] = "pending_confirmation"

    _save_item(inbox_item_id, result)
    return result


@router.get("/items")
async def ledger_items(limit: int = 50, offset: int = 0):
    """List submitted items, newest first."""
    items = []
    files = sorted(LEDGER_DATA.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for fp in files[offset:offset + limit]:
        try:
            items.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            pass
    return {"total": len(files), "items": items, "limit": limit, "offset": offset}


@router.get("/items/{inbox_item_id}")
async def ledger_get_item(inbox_item_id: str):
    """Get a single extraction result."""
    fp = LEDGER_DATA / f"{inbox_item_id}.json"
    if not fp.exists():
        return {"error": "not found", "inbox_item_id": inbox_item_id}
    return json.loads(fp.read_text(encoding="utf-8"))


@router.post("/items/{inbox_item_id}/confirm")
async def ledger_confirm(inbox_item_id: str, req: ConfirmRequest):
    """Confirm, reject, or edit a candidate."""
    fp = LEDGER_DATA / f"{inbox_item_id}.json"
    if not fp.exists():
        return {"error": "not found", "inbox_item_id": inbox_item_id}
    item = json.loads(fp.read_text(encoding="utf-8"))
    item["status"] = req.action
    item["confirmed_at"] = datetime.now(TZ).isoformat()
    _save_item(inbox_item_id, item)
    return item


@router.delete("/items/{inbox_item_id}")
async def ledger_delete_item(inbox_item_id: str):
    """Delete a submitted item."""
    fp = LEDGER_DATA / f"{inbox_item_id}.json"
    if not fp.exists():
        return {"error": "not found", "inbox_item_id": inbox_item_id}
    fp.unlink()
    return {"ok": True, "deleted": inbox_item_id}


@router.get("/summary")
async def ledger_summary():
    """Return a reconciliation summary of all items."""
    items = []
    for fp in sorted(LEDGER_DATA.glob("*.json"), key=lambda p: p.stat().st_mtime):
        try:
            items.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            pass

    total = len(items)
    confirmed = sum(1 for i in items if i.get("status") == "confirmed")
    pending = sum(1 for i in items if i.get("status") == "pending_confirmation")
    rejected = sum(1 for i in items if i.get("status") == "rejected")

    p0 = p1 = p2 = p3 = 0
    income = expense = refund = 0.0
    for item in items:
        for c in item.get("candidates", []):
            for rf in c.get("risk_flags", []):
                sev = rf.get("severity", "")
                if sev == "P0": p0 += 1
                elif sev == "P1": p1 += 1
                elif sev == "P2": p2 += 1
                elif sev == "P3": p3 += 1
            if c.get("target_table") == "MoneyFlow":
                amt = c.get("fields", {}).get("amount", 0)
                direction = c.get("fields", {}).get("direction", "")
                if direction == "income": income += amt
                elif direction == "expense": expense += amt
                elif direction == "refund": refund += amt

    return {
        "date": datetime.now(TZ).strftime("%Y-%m-%d"),
        "items": {"total": total, "confirmed": confirmed, "pending": pending, "rejected": rejected},
        "exceptions": {"P0": p0, "P1": p1, "P2": p2, "P3": p3},
        "cashflow": {"income": income, "expense": expense, "refund": refund, "net": income - expense + refund},
    }


def _save_item(inbox_item_id: str, data: dict):
    fp = LEDGER_DATA / f"{inbox_item_id}.json"
    fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
