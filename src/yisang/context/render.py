from .models import ContextPack

def render_context(pack: ContextPack) -> str:
    """Render a provider-neutral context pack into deterministic text."""
    lines = [
        "[YISANG IDENTITY]",
        f"agent_id: {pack.agent_id}",
        f"name: {pack.identity.get('name', '')}",
        "principles:",
    ]
    lines.extend(f"- {item}" for item in pack.identity.get("principles", []))

    lines.extend(["", "[STATE]"])
    for key in sorted(pack.state):
        lines.append(f"{key}: {pack.state[key]}")

    lines.extend(["", "[RELEVANT MEMORY]"])
    if pack.memories:
        for memory in pack.memories:
            lines.append(
                f"- ({memory['memory_id']}, {memory['kind']}, "
                f"confidence={memory['confidence']:.2f}) {memory['content']}"
            )
    else:
        lines.append("- none")

    lines.extend(["", "[ACTIVE E.G.O]"])
    if pack.egos:
        for ego in pack.egos:
            lines.append(f"- {ego['ego_id']}: {ego['name']}")
            if ego.get("instructions"):
                lines.append(f"  instructions: {ego['instructions']}")
    else:
        lines.append("- none")

    lines.extend(["", "[CONSTRAINTS]"])
    lines.extend(f"- {item}" for item in pack.constraints)

    lines.extend(["", "[USER REQUEST]", pack.user_text])
    return "\n".join(lines)
