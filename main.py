"""
main.py — Job Search Agent entry point.
Run this to kick off the full pipeline.
Currently wires: Search → Score → Save to DB
Next: → Notify → Apply → Outreach → Track
"""

import os
from memory.db  import init_db, insert_job, get_jobs_by_status
from modules.searcher import search_jobs
from modules.scorer   import score_jobs
# from modules.scorer_serp import 

def run():
    print("\n=== Job Search Agent Starting ===\n")

    # 1. Init DB (safe to call every time — creates tables if missing)
    os.makedirs("memory", exist_ok=True)
    init_db()

    # 2. Search all job boards
    raw_jobs = search_jobs()
    if not raw_jobs:
        print("[Main] No new jobs found. Try again later.")
        return

    # 3. Score against CV
    scored_jobs = score_jobs(raw_jobs)
    if not scored_jobs:
        print("[Main] No jobs passed the score threshold.")
        return

    # 4. Save to DB
    for job in scored_jobs:
        insert_job({
            "title":        job.get("title", ""),
            "company":      job.get("company", ""),
            "location":     job.get("location", ""),
            "url":          job.get("url", ""),
            "source":       job.get("source", ""),
            "score":        job.get("score", 0),
            "score_reason": job.get("reason", ""),
        })

    # 5. Print summary
    print("\n=== Jobs saved to DB ===")
    for job in scored_jobs:
        print(f"  [{job['score']}/10] {job.get('company','?')} — {job.get('title','?')}")
        print(f"         {job['url']}")
        print(f"         {job.get('reason','')}\n")

    print(f"\n[Main] Done. {len(scored_jobs)} jobs queued for your review.")
    print("[Main] Next step: run notifier.py to get Telegram alerts.\n")

if __name__ == "__main__":
    run()