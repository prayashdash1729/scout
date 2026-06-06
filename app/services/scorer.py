"""
Score one rendered job page against the candidate's CV using Gemini, returning
a validated JobEvaluation (structured output).
"""

from __future__ import annotations

import logging

from app.schemas import JobEvaluation
from app.services.gemini import generate_structured

log = logging.getLogger(__name__)

_PROMPT = """\
You are a precise job-fit evaluator for a job-search agent.

Today's date is {today}. Use it to judge how recent the posting is.

## Candidate CV
{cv}

## Candidate target roles
{roles}

## Candidate target cities
{cities}

## Page under evaluation
URL: {url}

### Page content (rendered)
{content}

## Instructions
1. Decide if this page is a SINGLE concrete job posting (not a list, not a
   company homepage, not an article). Set is_job_posting accordingly.
2. If it is NOT a job posting, set score to 0 and still return the other fields
   as best you can.
3. If it IS a job posting, score 0-10 how well THIS candidate fits, weighing
   role match, seniority match (the candidate is junior/early-career), required
   skills vs the CV, and location vs the target cities.
4. Extract a clean title, company, location, a direct apply/posting link, and
   the posting date if stated.
5. Produce job_key as 'companyslug|jobid' exactly as specified in the schema.
"""


async def evaluate(
    cv_text: str,
    url: str,
    content: str,
    *,
    today: str,
    target_roles: list[str],
    target_cities: list[str],
) -> JobEvaluation:
    prompt = _PROMPT.format(
        today=today,
        cv=cv_text[:18000],
        roles=", ".join(target_roles) or "(none specified)",
        cities=", ".join(target_cities) or "(none specified)",
        url=url,
        content=content[:18000],
    )
    return await generate_structured(prompt, JobEvaluation, temperature=0.2)
