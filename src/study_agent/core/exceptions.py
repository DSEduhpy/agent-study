"""Application-specific exceptions with safe, actionable messages."""


class StudyAgentError(Exception):
    """Base exception for expected Study Agent failures."""


class ConfigurationError(StudyAgentError):
    """Raised when application configuration is missing or invalid."""


class CurriculumError(StudyAgentError):
    """Raised when curriculum content cannot be loaded safely."""


class AIProviderError(StudyAgentError):
    """Raised for provider failures without exposing credentials."""


class DatabaseError(StudyAgentError):
    """Raised when persistence cannot complete."""
