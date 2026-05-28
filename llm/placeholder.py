"""PlaceholderLLM — mock provider for development and testing without API keys."""

import json
from typing import Optional

from llm.base import BaseLLM, LLMResponse
from utils.logger import logger

_MOCK_MATCH = {
    "score": 75,
    "reasons": [
        "Candidate has strong DevOps and cloud experience matching the role",
        "Kubernetes and Terraform skills align with job requirements",
    ],
    "missing_skills": ["ArgoCD", "Istio"],
    "recommendation": "apply",
    "seniority_match": True,
}

_MOCK_PROFILE = {
    "name": "Aditya Sharma",
    "email": "aditya@example.com",
    "phone": "+91-9999999999",
    "skills": [
        "Kubernetes", "Docker", "Terraform", "AWS", "GCP",
        "CI/CD", "Jenkins", "Python", "Linux", "Git",
        "Helm", "Ansible", "Prometheus", "Grafana",
    ],
    "experience_years": 3.5,
    "current_role": "DevOps Engineer",
    "education": "B.Tech Computer Science",
    "certifications": ["AWS Solutions Architect Associate", "CKA"],
    "summary": (
        "Experienced DevOps Engineer with 3.5+ years building cloud-native "
        "infrastructure on AWS and GCP. Expertise in Kubernetes, Terraform, "
        "and full CI/CD pipeline automation."
    ),
}

_MOCK_COVER = (
    "I am excited to apply for the {job_title} position at {company}. "
    "With over 3.5 years of hands-on DevOps and cloud engineering experience, "
    "I am confident in my ability to make an immediate impact on your "
    "infrastructure and deployment workflows.\n\n"
    "My experience with Kubernetes, Terraform, and AWS aligns directly with "
    "the requirements of this role. I have successfully designed and maintained "
    "multi-region cloud environments, built zero-downtime CI/CD pipelines, and "
    "implemented comprehensive monitoring solutions using Prometheus and Grafana.\n\n"
    "I would welcome the opportunity to discuss how my skills can contribute "
    "to your team. Thank you for considering my application. "
    "[PLACEHOLDER — set LLM_PROVIDER=gemini or deepseek in .env for real letters]"
)


class PlaceholderLLM(BaseLLM):
    """Mock LLM provider that returns hard-coded responses. No API key required."""

    MODEL_NAME: str = "placeholder-v1.0"

    async def complete(self, prompt: str, system: Optional[str] = None) -> LLMResponse:
        lower = prompt.lower()

        if any(k in lower for k in ("match", "score", "evaluate", "fit")):
            content = json.dumps(_MOCK_MATCH)
            logger.debug("PlaceholderLLM returning mock match response")

        elif any(k in lower for k in ("cover letter", "cover_letter", "apply for")):
            job_title, company = "the position", "your company"
            for line in prompt.splitlines():
                if "role:" in line.lower():
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        job_title = parts[1].strip()
                if "company:" in line.lower():
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        company = parts[1].strip()
            content = _MOCK_COVER.format(job_title=job_title, company=company)
            logger.debug("PlaceholderLLM returning mock cover letter")

        elif any(k in lower for k in ("extract", "profile", "resume", "candidate")):
            content = json.dumps(_MOCK_PROFILE)
            logger.debug("PlaceholderLLM returning mock profile response")

        else:
            content = (
                "PlaceholderLLM: configure LLM_PROVIDER=gemini|deepseek|ollama|groq in .env"
            )

        return LLMResponse(content=content, model=self.MODEL_NAME, tokens_used=0)

    def is_available(self) -> bool:
        return True
