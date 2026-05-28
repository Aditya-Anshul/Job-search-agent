"""SQLAlchemy ORM models: Job, RunHistory, CandidateProfile."""

from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    """Master job registry — one row per unique discovered job listing."""

    __tablename__ = "jobs"

    id = Column(String, primary_key=True, nullable=False)
    platform = Column(String, nullable=False)
    title = Column(String, nullable=False)
    company = Column(String)
    location = Column(String)
    description = Column(Text)
    url = Column(String)
    posted_date = Column(String)
    salary = Column(String)
    experience_required = Column(String)

    match_score = Column(Float, default=0.0)
    match_reasons = Column(Text)
    missing_skills = Column(Text)

    status = Column(String, default="discovered")
    is_easy_apply = Column(Boolean, default=False)
    cover_letter = Column(Text)
    applied_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    def __repr__(self) -> str:
        return f"<Job id={self.id!r} title={self.title!r} status={self.status!r}>"


class RunHistory(Base):
    """Aggregate statistics for each scheduled agent run."""

    __tablename__ = "run_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_at = Column(DateTime(timezone=True), default=_utcnow)
    jobs_discovered = Column(Integer, default=0)
    jobs_matched = Column(Integer, default=0)
    jobs_applied = Column(Integer, default=0)
    jobs_failed = Column(Integer, default=0)
    jobs_skipped = Column(Integer, default=0)
    platforms_scraped = Column(Text)
    duration_seconds = Column(Float)
    status = Column(String, default="success")
    error_message = Column(Text)

    def __repr__(self) -> str:
        return f"<RunHistory id={self.id} applied={self.jobs_applied} status={self.status!r}>"


class CandidateProfile(Base):
    """Versioned snapshots of LLM-extracted candidate profile from resume."""

    __tablename__ = "candidate_profile"

    id = Column(Integer, primary_key=True, autoincrement=True)
    extracted_at = Column(DateTime(timezone=True), default=_utcnow)
    name = Column(String)
    email = Column(String)
    phone = Column(String)
    skills = Column(Text)
    experience_years = Column(Float)
    current_role = Column(String)
    education = Column(String)
    certifications = Column(Text)
    summary = Column(Text)
    raw_resume_text = Column(Text)

    def __repr__(self) -> str:
        return f"<CandidateProfile id={self.id} name={self.name!r}>"
