"""Agent cover letter generator — LLM-powered tailored cover letter creation."""

from llm import get_llm
from utils.logger import logger

SYSTEM_MSG = (
    "You are a professional career coach specialising in technology roles. "
    "Write concise, impactful cover letters that highlight specific skills and achievements. "
    "Return ONLY the cover letter text — no subject line, no 'Dear Hiring Manager:' label, "
    "no explanation, no markdown."
)

_MAX_COVER_LEN = 1500


def _build_cover_prompt(job_title: str, company: str, job_description: str, profile: dict) -> str:
    skills_str = ", ".join(profile.get("skills", [])[:10])
    return f"""Write a professional cover letter for the following job application.

CANDIDATE:
- Name: {profile.get('name', 'The Candidate')}
- Current Role: {profile.get('current_role', 'DevOps Engineer')}
- Experience: {profile.get('experience_years', 3.5)} years
- Key Skills: {skills_str}
- Summary: {profile.get('summary', '')[:300]}

JOB DETAILS:
- Role: {job_title}
- Company: {company}
- Description: {job_description[:1000]}

Write EXACTLY 3 short paragraphs:
1. Hook: Reference the specific role and company. Show genuine interest.
2. Skills: Highlight 2-3 relevant skills with concrete examples.
3. Call to action: Express enthusiasm and invite further conversation.

Maximum 200 words total. Professional but not generic. No placeholders."""


async def generate_cover_letter(
    job_title: str,
    company: str,
    job_description: str,
    profile: dict,
) -> str:
    """Generate a tailored cover letter for a matched job.

    Returns a minimal fallback letter on any error.
    """
    try:
        llm = get_llm()
        prompt = _build_cover_prompt(job_title, company, job_description, profile)
        resp = await llm.complete(prompt, system=SYSTEM_MSG)

        letter = resp.content.strip()
        if not letter:
            logger.warning(f"CoverLetter empty response for: {job_title} @ {company}")
            return _fallback_letter(job_title, company, profile)

        logger.info(f"CoverLetter generated: {len(letter)} chars for {job_title} @ {company}")
        return letter
    except Exception as e:
        logger.error(f"CoverLetter generation failed for '{job_title}': {e}")
        return _fallback_letter(job_title, company, profile)


def truncate_for_form(cover_letter: str) -> str:
    """Truncate cover letter to max length for web form submission."""
    if len(cover_letter) > _MAX_COVER_LEN:
        logger.debug(f"CoverLetter truncated from {len(cover_letter)} to {_MAX_COVER_LEN} chars")
        return cover_letter[:_MAX_COVER_LEN]
    return cover_letter


def _fallback_letter(job_title: str, company: str, profile: dict) -> str:
    name = profile.get("name", "I")
    role = profile.get("current_role", "DevOps Engineer")
    exp = profile.get("experience_years", 3.5)
    skills = ", ".join(profile.get("skills", [])[:5])
    return (
        f"I am excited to apply for the {job_title} position at {company}. "
        f"With {exp}+ years of experience as a {role}, I am confident in my "
        f"ability to contribute meaningfully to your team from day one.\n\n"
        f"My technical expertise includes {skills}, which aligns well with "
        f"the requirements of this role. I have successfully delivered complex "
        f"infrastructure projects and am passionate about building scalable, "
        f"reliable systems.\n\n"
        f"I would welcome the opportunity to discuss how my background can "
        f"benefit {company}. Thank you for considering my application."
    )
