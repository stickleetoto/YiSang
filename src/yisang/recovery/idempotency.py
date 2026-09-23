from __future__ import annotations

from hashlib import sha256
import json
from typing import Any


def side_effect_request_digest(
    tool_id: str,
    arguments: dict[str, Any],
) -> str:
    if not tool_id.strip():
        raise ValueError("tool_id must be non-empty")
    payload = json.dumps(
        {
            "tool_id": tool_id,
            "arguments": arguments,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + sha256(payload).hexdigest()



def side_effect_result_ref(tool_id: str, output: Any) -> str:
    if not tool_id.strip():
        raise ValueError("tool_id must be non-empty")
    payload = json.dumps(
        {
            "tool_id": tool_id,
            "output": output,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "result:sha256:" + sha256(payload).hexdigest()
