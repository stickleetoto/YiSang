from .models import EgoManifest

class CapabilityRouter:
    def route(self, query: str, egos: list[EgoManifest], *, limit: int = 3) -> list[EgoManifest]:
        q = query.lower()
        ranked = []
        for ego in egos:
            score = sum(1 for kw in ego.keywords if kw.lower() in q)
            if score:
                ranked.append((score, ego))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [ego for _, ego in ranked[:limit]]
