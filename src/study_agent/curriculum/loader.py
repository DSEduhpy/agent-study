"""Safe Markdown curriculum loader."""

from pathlib import Path
import re

from study_agent.core.exceptions import CurriculumError
from study_agent.core.models import Lesson


class CurriculumLoader:
    """Discover and load lessons below a controlled curriculum root."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise CurriculumError(
                f"Curriculum directory not found: {self.root}")

    def list_lessons(self) -> list[str]:
        """Return stable, relative lesson identifiers for Markdown files."""
        return sorted(path.relative_to(self.root).with_suffix("").as_posix() for path in self.root.rglob("*.md"))

    def load(self, lesson_id: str) -> Lesson:
        """Load one lesson after rejecting absolute and traversal paths."""
        if not lesson_id or Path(lesson_id).is_absolute() or "\\" in lesson_id:
            raise CurriculumError("Invalid lesson path")
        relative = Path(lesson_id)
        if relative.suffix != ".md":
            relative = relative.with_suffix(".md")
        candidate = (self.root / relative).resolve()
        if self.root not in candidate.parents or candidate.suffix.lower() != ".md":
            raise CurriculumError(
                "Lesson path escapes the curriculum directory")
        if not candidate.is_file():
            raise CurriculumError(f"Lesson not found: {lesson_id}")
        try:
            content = candidate.read_text(encoding="utf-8")
        except OSError as exc:
            raise CurriculumError("Could not read lesson") from exc
        title_match = re.search(r"^#\s+(.+?)\s*$", content, re.MULTILINE)
        if not title_match:
            raise CurriculumError("Lesson must contain a Markdown H1 title")
        parts = candidate.relative_to(self.root).parts
        if len(parts) < 3:
            raise CurriculumError(
                "Lesson path must include area and topic directories")
        return Lesson(candidate.stem, title_match.group(1), parts[0], "/".join(parts[1:-1]), content, candidate.as_posix())
