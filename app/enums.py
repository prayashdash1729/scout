"""Shared enumerations used across the data model and the bot."""

from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    """Lifecycle of a job within a single user's pipeline."""

    PENDING = "pending"      # surfaced, awaiting the user's approve/discard
    PERSISTED = "persisted"  # user approved — kept
    DISCARDED = "discarded"  # user rejected


class JobSource(str, Enum):
    """Which board a job URL came from (inferred from the host)."""

    LINKEDIN = "linkedin"
    NAUKRI = "naukri"
    INSTAHYRE = "instahyre"
    WELLFOUND = "wellfound"
    INDEED = "indeed"
    FOUNDIT = "foundit"
    HIRIST = "hirist"
    OTHER = "other"

    @classmethod
    def from_url(cls, url: str) -> "JobSource":
        u = (url or "").lower()
        mapping = {
            "linkedin.com": cls.LINKEDIN,
            "naukri.com": cls.NAUKRI,
            "instahyre.com": cls.INSTAHYRE,
            "wellfound.com": cls.WELLFOUND,
            "angel.co": cls.WELLFOUND,
            "indeed.": cls.INDEED,
            "foundit.in": cls.FOUNDIT,
            "monster.com": cls.FOUNDIT,
            "hirist.com": cls.HIRIST,
            "hirist.tech": cls.HIRIST,
        }
        for needle, src in mapping.items():
            if needle in u:
                return src
        return cls.OTHER


class ConvState(int, Enum):
    """Conversation states for the onboarding / CV-edit flows."""

    NAME = 0
    CV = 1
    ROLES = 2
    CITIES = 3
    EXPERIENCE = 4
    EDIT_CV = 5
