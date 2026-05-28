"""JobRepository — all database CRUD operations via SQLAlchemy ORM."""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings
from database.models import Base, CandidateProfile, Job, RunHistory
from utils.logger import logger

os.makedirs("data", exist_ok=True)

_engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)

Base.metadata.create_all(_engine)
SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)

logger.debug("Database engine initialised and tables created")


class JobRepository:
    """Repository class encapsulating all database access patterns."""

    def _get_session(self) -> Session:
        return SessionLocal()

    def job_exists(self, job_id: str) -> bool:
        """Check if a job with the given ID already exists."""
        with self._get_session() as session:
            result = session.query(Job.id).filter(Job.id == job_id).first()
            return result is not None

    def save_job(self, job: Job) -> bool:
        """Insert a new job record if it does not already exist."""
        try:
            with self._get_session() as session:
                existing = session.get(Job, job.id)
                if existing:
                    return False
                session.add(job)
                session.commit()
                logger.debug(f"Database job saved: {job.id}")
                return True
        except Exception as e:
            logger.error(f"Database save_job failed for {job.id}: {e}")
            return False

    def update_job_status(self, job_id: str, status: str, **kwargs) -> bool:
        """Update the status and optional fields of an existing job."""
        try:
            with self._get_session() as session:
                job = session.get(Job, job_id)
                if not job:
                    logger.warning(f"Database job not found for update: {job_id}")
                    return False
                job.status = status
                for field, value in kwargs.items():
                    if hasattr(job, field):
                        setattr(job, field, value)
                session.commit()
                return True
        except Exception as e:
            logger.error(f"Database update_job_status failed for {job_id}: {e}")
            return False

    def get_applied_count_today(self) -> int:
        """Count applications submitted today (UTC date)."""
        try:
            with self._get_session() as session:
                today = datetime.now(timezone.utc).date()
                count = (
                    session.query(func.count(Job.id))
                    .filter(
                        Job.status == "applied",
                        func.date(Job.applied_at) == today,
                    )
                    .scalar()
                )
                return count or 0
        except Exception as e:
            logger.error(f"Database get_applied_count_today failed: {e}")
            return 0

    def save_run(self, run: RunHistory) -> bool:
        """Persist a RunHistory record at the end of every agent run."""
        try:
            with self._get_session() as session:
                session.add(run)
                session.commit()
                logger.debug(f"Database RunHistory saved: id={run.id}")
                return True
        except Exception as e:
            logger.error(f"Database save_run failed: {e}")
            return False

    def save_profile(self, profile_data: dict) -> bool:
        """Insert a new CandidateProfile snapshot extracted from the resume."""
        try:
            with self._get_session() as session:
                profile = CandidateProfile(
                    name=profile_data.get("name", ""),
                    email=profile_data.get("email", ""),
                    phone=profile_data.get("phone", ""),
                    skills=json.dumps(profile_data.get("skills", [])),
                    experience_years=float(profile_data.get("experience_years", 0)),
                    current_role=profile_data.get("current_role", ""),
                    education=profile_data.get("education", ""),
                    certifications=json.dumps(profile_data.get("certifications", [])),
                    summary=profile_data.get("summary", ""),
                    raw_resume_text=profile_data.get("raw_resume_text", ""),
                )
                session.add(profile)
                session.commit()
                logger.debug(f"Database CandidateProfile saved: id={profile.id}")
                return True
        except Exception as e:
            logger.error(f"Database save_profile failed: {e}")
            return False

    def get_latest_profile(self) -> Optional[CandidateProfile]:
        """Retrieve the most recently extracted candidate profile."""
        try:
            with self._get_session() as session:
                return (
                    session.query(CandidateProfile)
                    .order_by(CandidateProfile.extracted_at.desc())
                    .first()
                )
        except Exception as e:
            logger.error(f"Database get_latest_profile failed: {e}")
            return None


# Module-level singleton
repo = JobRepository()
