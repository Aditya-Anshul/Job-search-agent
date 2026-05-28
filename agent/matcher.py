"""Agent matcher — LLM-powered job match scoring."""

import json
from typing import Any, Dict

from llm import get_llm
from utils.logger import clean_json, logger

SYSTEM_MSG = (
    "You are an expert technical recruiter with deep knowledge of Cloud, "
    "DevOps, MLOps, and AI engineering roles. Evaluate the job fit for the "
    "candidate based on their resume and profile. "
    "Return ONLY valid JSON — no explanation, no markdown, no code fences."
)

_SAFE_FALLBACK: Dict[str, Any] = {
    "score": 0,
    "reasons": ["Match scoring failed — JSON parse error"],
    "missing_skills": [],
    "recommendation": "skip",
    "seniority_match": False,
}


def _build_match_prompt(job_title: str, job_description: str, profile: dict, resume_text: str) -> str:
    skills_str = ", ".join(profile.get("skills", [])[:10])
    return f"""Evaluate this job for the following candidate and return a JSON match score.

CANDIDATE PROFILE:
- Current Role: {profile.get('current_role', 'Not specified')}
- Experience: {profile.get('experience_years', 0)} years
- Top Skills: {skills_str}
- Summary: {profile.get('summary', '')[:300]}

RESUME EXCERPT:
{resume_text[:2000]}

JOB TO EVALUATE:
- Title: {job_title}
- Description: {job_description[:2000]}

Return ONLY this JSON (no other text):
{{
  "score": <integer 0-100>,
  "reasons": ["<reason 1>", "<reason 2>"],
  "missing_skills": ["<skill 1>", "<skill 2>"],
  "recommendation": "apply" or "skip",
  "seniority_match": true or false
}}

Return ONLY the JSON. Do not include any other text."""


async def match_job(
    job_title: str,
    job_description: str,
    profile: dict,
    resume_text: str,
) -> Dict[str, Any]:
    """Score a job listing against the candidate profile using LLM.

    Returns safe fallback dict (score=0, recommendation=skip) on any error.
    """
    try:
        llm = get_llm()
        prompt = _build_match_prompt(job_title, job_description, profile, resume_text)
        resp = await llm.complete(prompt, system=SYSTEM_MSG)

        clean = clean_json(resp.content)
        if not clean:
            logger.warning(f"Matcher empty response for: {job_title}")
            return _SAFE_FALLBACK.copy()

        data = json.loads(clean)
        score = int(data.get("score", 0))
        recommendation = data.get("recommendation", "skip")
        reasons = data.get("reasons", [])
        missing = data.get("missing_skills", [])
        seniority = bool(data.get("seniority_match", False))

        logger.info(f"Matcher {job_title}: score={score}, recommendation={recommendation}")
        return {
            "score": score,
            "reasons": reasons,
            "missing_skills": missing,
            "recommendation": recommendation,
            "seniority_match": seniority,
        }
    except json.JSONDecodeError as e:
        logger.warning(f"Matcher JSON parse failed for '{job_title}': {e}")
        return _SAFE_FALLBACK.copy()
    except Exception as e:
        logger.warning(f"Matcher unexpected error for '{job_title}': {e}")
        return _SAFE_FALLBACK.copy()
