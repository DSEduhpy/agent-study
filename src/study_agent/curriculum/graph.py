"""Small directed knowledge graph used by curriculum reasoning."""

from __future__ import annotations

from study_agent.core.models import KnowledgeNode, KnowledgeRelation


class KnowledgeGraph:
    """In-memory graph with cycle protection for prerequisite edges."""

    def __init__(self) -> None:
        self.nodes: dict[str, KnowledgeNode] = {}
        self.relations: set[KnowledgeRelation] = set()

    def add_node(self, node: KnowledgeNode) -> None:
        self.nodes[node.id] = node

    def add_relation(self, relation: KnowledgeRelation) -> None:
        if relation.source_id not in self.nodes or relation.target_id not in self.nodes:
            raise KeyError("knowledge relation requires existing nodes")
        if relation.relation_type == "prerequisite" and self._reachable(relation.target_id, relation.source_id):
            raise ValueError("prerequisite relation would create a cycle")
        self.relations.add(relation)

    def prerequisites(self, node_id: str, *, recursive: bool = False) -> list[KnowledgeNode]:
        ids = self._targets(node_id, "prerequisite")
        if recursive:
            ids = self._closure(ids, "prerequisite")
        return [self.nodes[item] for item in sorted(ids) if item in self.nodes]

    def dependents(self, node_id: str, *, recursive: bool = False) -> list[KnowledgeNode]:
        ids = {relation.source_id for relation in self.relations if relation.target_id == node_id and relation.relation_type == "prerequisite"}
        if recursive:
            ids = self._reverse_closure(ids)
        return [self.nodes[item] for item in sorted(ids) if item in self.nodes]

    def related(self, node_id: str, relation_type: str | None = None) -> list[KnowledgeNode]:
        ids = {relation.target_id for relation in self.relations if relation.source_id == node_id and (relation_type is None or relation.relation_type == relation_type)}
        return [self.nodes[item] for item in sorted(ids) if item in self.nodes]

    def _targets(self, node_id: str, relation_type: str) -> set[str]:
        return {relation.target_id for relation in self.relations if relation.source_id == node_id and relation.relation_type == relation_type}

    def _reachable(self, start: str, target: str) -> bool:
        pending = [start]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == target:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(self._targets(current, "prerequisite"))
        return False

    def _closure(self, ids: set[str], relation_type: str) -> set[str]:
        result = set(ids)
        for node_id in tuple(ids):
            result.update(self._closure(self._targets(node_id, relation_type), relation_type))
        return result

    def _reverse_closure(self, ids: set[str]) -> set[str]:
        result = set(ids)
        for node_id in tuple(ids):
            result.update(self._reverse_closure({item.id for item in self.dependents(node_id)}))
        return result