from datetime import datetime
from typing import Optional


def fmt_seconds(secs) -> str:
    if secs is None:
        return "—"
    secs = int(secs)
    h, rem = divmod(secs, 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    return f"{m}m {s}s" if m else f"{s}s"


def fmt_duration(started: str, ended: Optional[str]) -> str:
    if not ended:
        return "—"
    try:
        secs = int(
            (datetime.fromisoformat(ended) - datetime.fromisoformat(started))
            .total_seconds()
        )
        return fmt_seconds(max(secs, 0) or None)
    except Exception:
        return "—"


def fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%-d %b %Y  %H:%M")
    except Exception:
        return iso
