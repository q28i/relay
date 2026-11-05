"""
Content Collections API Router.
Handles reusable collections of message templates and media assets with 3 pairing modes:
1. fixed_pair: one selected message and one selected media asset per recipient.
2. approved_combinations: explicitly defined valid message-media pairs.
3. balanced_testing: rule-based or balanced assignment across approved combinations.
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query
from backend.database import db
from backend.models import CollectionCreate, CollectionUpdate
from logger import get_logger

logger = get_logger("CollectionsRouter")
router = APIRouter(prefix="/api/collections", tags=["Content Collections"])


@router.get("")
def list_collections():
    """Lists all reusable content collections with their associated messages and media."""
    return db.get_collections()


@router.post("")
def create_content_collection(payload: CollectionCreate):
    """Creates a new named content collection containing messages and media."""
    try:
        col_id = db.create_collection(
            name=payload.name,
            description=payload.description,
            pairing_mode=payload.pairing_mode,
            message_ids=payload.message_ids,
            media_ids=payload.media_ids,
            pairs=payload.pairs
        )
        return db.get_collection(col_id)
    except Exception as e:
        logger.error(f"Failed to create collection: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{col_id}")
def get_single_collection(col_id: int):
    """Retrieves full details of a specific collection."""
    col = db.get_collection(col_id)
    if not col:
        raise HTTPException(status_code=404, detail="Content collection not found")
    return col


@router.put("/{col_id}")
def update_content_collection(col_id: int, payload: CollectionUpdate):
    """Updates a content collection's metadata, items, or approved pairs."""
    updated = db.update_collection(
        collection_id=col_id,
        name=payload.name,
        description=payload.description,
        pairing_mode=payload.pairing_mode,
        message_ids=payload.message_ids,
        media_ids=payload.media_ids,
        pairs=payload.pairs
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Content collection not found")
    return updated


@router.delete("/{col_id}")
def delete_content_collection(col_id: int):
    """Deletes a content collection."""
    success = db.delete_collection(col_id)
    if not success:
        raise HTTPException(status_code=404, detail="Content collection not found")
    return {"success": True, "deleted_id": col_id}

