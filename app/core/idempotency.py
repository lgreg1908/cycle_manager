import hashlib
import json
from datetime import datetime
from typing import Any, Tuple

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.idempotency import IdempotencyKey
from app.models.user import User


def _hash_payload(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def begin_idempotent_request(
    *,
    db: Session,
    user: User,
    key: str,
    method: str,
    route: str,
    payload_for_hash: Any | None = None,
) -> Tuple[IdempotencyKey, bool]:
    """
    Returns (idem_row, is_new).
    - If existing COMPLETED -> caller should return saved response immediately.
    - If existing IN_PROGRESS -> 409 (client should retry later).
    - If existing but hash differs -> 409 conflict.
    """
    req_hash = _hash_payload(payload_for_hash) if payload_for_hash is not None else None

    existing = (
        db.query(IdempotencyKey)
        .filter(IdempotencyKey.user_id == user.id, IdempotencyKey.key == key)
        .one_or_none()
    )

    if existing:
        if existing.request_hash and req_hash and existing.request_hash != req_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency-Key reuse with different request body",
            )

        if existing.status == "COMPLETED":
            return existing, False

        if existing.status == "IN_PROGRESS":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Request with this Idempotency-Key is already in progress",
            )

        # FAILED -> allow retry; mark in-progress
        existing.status = "IN_PROGRESS"
        existing.updated_at = datetime.utcnow()
        db.flush()
        return existing, False

    row = IdempotencyKey(
        user_id=user.id,
        key=key,
        method=method,
        route=route,
        request_hash=req_hash,
        status="IN_PROGRESS",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(row)

    try:
        db.flush()
    except IntegrityError:
        # Someone else inserted first (same tx window / concurrent request)
        # NOTE: do NOT rollback here; let caller own rollback.
        existing = (
            db.query(IdempotencyKey)
            .filter(IdempotencyKey.user_id == user.id, IdempotencyKey.key == key)
            .one()
        )
        if existing.status == "COMPLETED":
            return existing, False
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key collision (try again)",
        )

    return row, True


def complete_idempotent_request(
    *,
    db: Session,
    row: IdempotencyKey,
    response_code: int,
    response_body: dict | list | None,
):
    row.status = "COMPLETED"
    row.response_code = response_code
    row.response_body = response_body
    row.updated_at = datetime.utcnow()
    db.flush()


def fail_idempotent_request(*, db: Session, row: IdempotencyKey):
    row.status = "FAILED"
    row.updated_at = datetime.utcnow()
    db.flush()
