from __future__ import annotations

from fastapi import HTTPException, Response, status


def parse_if_match(if_match: str | None) -> int:
    """
    Supports:
      If-Match: 3
      If-Match: "3"
    """
    if if_match is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="Missing If-Match header (expected current version)",
        )

    raw = if_match.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        raw = raw[1:-1]

    try:
        v = int(raw)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid If-Match header (expected integer version)",
        )

    if v <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid If-Match header (version must be positive)",
        )
    return v


def assert_version_matches(*, current_version: int, if_match_version: int) -> None:
    if current_version != if_match_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Stale version",
                "expected": current_version,
                "got": if_match_version,
            },
        )


def set_etag(response: Response, version: int) -> None:
    # Quote it to behave like a real ETag
    response.headers["ETag"] = f'"{version}"'
