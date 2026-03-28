"""
Module 2: Score each job listing against the candidate's CV.
Uses Gemini via Vertex AI service account credentials.
"""

import json
import PyPDF2
import vertexai
from vertexai.generative_models import GenerativeModel
from config import CANDIDATE, SCORE_THRESHOLD, GOOGLE_CLOUD_PROJECT

vertexai.init(project=GOOGLE_CLOUD_PROJECT, location="us-central1")
_model   = GenerativeModel("gemini-2.0-flash")
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
        resp = _model.generate_content(prompt)
        text = resp.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)

    except Exception as e:
        print(f"[Score] Error scoring job: {e}")
        return {
            "score": 0, "reason": f"Scoring failed: {e}",
            "title": job.get("title", ""), "company": "",
            "location": "", "is_junior": False,
            "key_match": [], "red_flags": ["scoring_error"]
        }