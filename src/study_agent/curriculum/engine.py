"""Curriculum index and knowledge-graph orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from study_agent.core.models import Difficulty, KnowledgeNode, KnowledgeRelation
from study_agent.curriculum.graph import KnowledgeGraph
from study_agent.curriculum.loader import CurriculumLoader
from study_agent.memory.repository import LearningRepository


class CurriculumEngine:
    """Expose curriculum search and graph queries without replacing CurriculumLoader."""

    def __init__(self, root: Path | str = "curriculum", repository: LearningRepository | None = None) -> None:
        self.loader = CurriculumLoader(root)
        self.repository = repository
        self.graph = KnowledgeGraph()
        self._load_index()

    def find(self, query: str) -> list[KnowledgeNode]:
        needle = query.strip().casefold()
        return [node for node in self.graph.nodes.values() if node.id.casefold() == needle or node.matches(query) or needle in node.description.casefold()]

    def list_subjects(self) -> list[str]:
        return sorted({node.subject for node in self.graph.nodes.values() if node.subject})

    def list_topics(self, subject: str | None = None) -> list[str]:
        return sorted({node.topic for node in self.graph.nodes.values() if node.topic and (subject is None or node.subject.casefold() == subject.casefold())})

    def get_node(self, query: str) -> KnowledgeNode:
        matches = self.find(query)
        if not matches:
            raise KeyError(f"knowledge node not found: {query}")
        return matches[0]

    def prerequisites(self, query: str, *, recursive: bool = False) -> list[KnowledgeNode]:
        return self.graph.prerequisites(self.get_node(query).id, recursive=recursive)

    def dependents(self, query: str, *, recursive: bool = False) -> list[KnowledgeNode]:
        return self.graph.dependents(self.get_node(query).id, recursive=recursive)

    def next_concepts(self, query: str | None = None) -> list[KnowledgeNode]:
        if query is None:
            return [node for node in self.graph.nodes.values() if not self.graph.prerequisites(node.id)]
        node = self.get_node(query)
        return self.graph.dependents(node.id)

    def _load_index(self) -> None:
        index_path = self.loader.root / "knowledge.yaml"
        if not index_path.is_file():
            return
        data = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
        for raw in data.get("nodes", []):
            node = KnowledgeNode(
                id=str(raw["id"]), name=str(raw["name"]), description=str(raw.get("description", "")),
                area=str(raw.get("area", "")), subject=str(raw.get("subject", "")), module=str(raw.get("module", "")),
                topic=str(raw.get("topic", "")), type=str(raw.get("type", "concept")),
                difficulty=Difficulty(str(raw.get("difficulty", "beginner"))),
                learning_objectives=_strings(raw.get("learning_objectives")), prerequisites=_strings(raw.get("prerequisites")),
                skills=_strings(raw.get("skills")), aliases=_strings(raw.get("aliases")), tags=_strings(raw.get("tags")),
            )
            self.graph.add_node(node)
            if self.repository:
                self.repository.save_knowledge_node(node)
        for raw in data.get("relations", []):
            relation = KnowledgeRelation(str(raw["source"]), str(raw["target"]), str(raw.get("type", "related")))
            self.graph.add_relation(relation)
            if self.repository:
                self.repository.save_knowledge_relation(relation)


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    return tuple(str(item) for item in value)