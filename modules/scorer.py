"""
Module 2: Score each job listing against the candidate's CV.
Uses Groq (free) instead of Claude API.
"""

import json
import PyPDF2
from groq import Groq
from config import CANDIDATE, SCORE_THRESHOLD

_client = Groq()   # reads GROQ_API_KEY from env automatically
_cv_text = None

def _load_cv() -> str:
    global _cv_text
    if _cv_text:
        return _cv_text
    with open(CANDIDATE["cv_path"], "rb") as f:
        reader = PyPDF2.PdfReader(f)
        _cv_text = "\n".join(p.extract_text() for p in reader.pages)
    return _cv_text

def score_jobs(raw_jobs: list[dict]) -> list[dict]:
    cv = _load_cv()
    scored = []
    for job in raw_jobs:
        result = _score_single(job, cv)
        if result["score"] >= SCORE_THRESHOLD:
            scored.append({**job, **result})
            print(f"[Score] ✓ {result['score']}/10 — {result.get('company','?')} | {result.get('title','?')}")
        else:
            print(f"[Score] ✗ {result['score']}/10 — skipped")
    scored.sort(key=lambda x: x["score"], reverse=True)
    print(f"[Score] {len(scored)} jobs passed threshold.")
    return scored

def _score_single(job: dict, cv: str) -> dict:
    prompt = f"""
You are a job fit evaluator. Given a candidate's CV and a job posting snippet,
evaluate how well the candidate fits.

## Candidate CV
{cv}

## Job Posting
Title: {job['title']}
URL: {job['url']}
Snippet: {job['snippet']}

## Task
Return a JSON object with ONLY these fields. No markdown, no explanation, just raw JSON:
{{
  "score": <integer 1-10>,
  "reason": "<2-3 sentence explanation>",
  "title": "<clean job title>",
  "company": "<company name>",
  "location": "<city>",
  "is_junior": <true or false>,
  "key_match": ["<matching skill>", ...],
  "red_flags": ["<any concern>", ...]
}}
"""
    try:
        resp = _client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # or "mixtral-8x7b-32768"
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.1,   # low temp = more consistent JSON
        )
        text = resp.choices[0].message.content.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)

    except Exception as e:
        print(f"[Score] Error: {e}")
        return {
            "score": 0, "reason": f"Scoring failed: {e}",
            "title": job.get("title", ""), "company": "",
            "location": "", "is_junior": False,
            "key_match": [], "red_flags": ["scoring_error"]
        }