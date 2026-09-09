from dataclasses import dataclass, field

@dataclass
class AuditEvent:
    request_id: str
    event_type: str
    detail: dict = field(default_factory=dict)
