"""
test_modules.py — Run this before main.py to verify each piece works.
Usage: uv run python test_modules.py
"""

import os, json, sys

def header(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")

def ok(msg):  print(f"  ✓ {msg}")
def fail(msg): print(f"  ✗ {msg}"); sys.exit(1)

# ── Test 1: Imports ───────────────────────────────────────
header("TEST 1: Imports")
try:
    import anthropic; ok("anthropic")
    import tavily;    ok("tavily")
    import PyPDF2;    ok("PyPDF2")
    from dotenv import load_dotenv; ok("dotenv")
    load_dotenv()
except ImportError as e:
    fail(f"Missing package: {e}. Run: uv add <package>")

# ── Test 2: Env vars ──────────────────────────────────────
header("TEST 2: Environment Variables")
for key in ["ANTHROPIC_API_KEY", "TAVILY_API_KEY"]:
    val = os.getenv(key)
    if val:
        ok(f"{key} = {val[:8]}...")
    else:
        fail(f"{key} is missing from .env")

# ── Test 3: DB ────────────────────────────────────────────
header("TEST 3: Database Init")
try:
    os.makedirs("memory", exist_ok=True)
    from memory.db import init_db, insert_job, get_jobs_by_status, job_exists
    init_db()
    ok("DB initialized")

    # Insert a dummy job
    insert_job({
        "title": "Test DS Role",
        "company": "Test Corp",
        "location": "Bangalore",
        "url": "https://test.example.com/job/1",
        "source": "test",
        "score": 8,
        "score_reason": "Test entry"
    })
    ok("Insert job works")

    # Check dedup
    assert job_exists("https://test.example.com/job/1"), "job_exists failed"
    ok("Dedup (job_exists) works")

    # Check retrieval
    jobs = get_jobs_by_status("seen")
    assert any(j["url"] == "https://test.example.com/job/1" for j in jobs)
    ok(f"get_jobs_by_status works — found {len(jobs)} job(s)")

except Exception as e:
    fail(f"DB error: {e}")

# ── Test 4: CV loading ────────────────────────────────────
header("TEST 4: CV / Resume")
cv_path = "cv/resume.pdf"
if not os.path.exists(cv_path):
    fail(f"Resume not found at '{cv_path}'. Drop your PDF there.")
try:
    import PyPDF2
    with open(cv_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        text = "\n".join(p.extract_text() for p in reader.pages)
    if len(text.strip()) < 100:
        fail("CV text is too short — PDF might be image-based. Try a text-based PDF.")
    ok(f"CV loaded — {len(text)} characters across {len(reader.pages)} page(s)")
except Exception as e:
    fail(f"CV read error: {e}")

# ── Test 5: Tavily search ─────────────────────────────────
header("TEST 5: Tavily Search (1 query)")
try:
    from tavily import TavilyClient
    client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    results = client.search(
        query="junior data scientist jobs Bangalore site:linkedin.com",
        max_results=3
    )
    hits = results.get("results", [])
    if not hits:
        fail("Tavily returned 0 results — check your API key")
    ok(f"Tavily returned {len(hits)} result(s)")
    for r in hits:
        print(f"     • {r.get('title','?')[:60]}")
        print(f"       {r.get('url','')[:70]}")
except Exception as e:
    fail(f"Tavily error: {e}")

# ── Test 6: Claude scorer (1 job) ─────────────────────────
header("TEST 6: Claude Scorer (1 job)")
try:
    from modules.scorer import _score_single, _load_cv
    cv = _load_cv()

    dummy_job = {
        "title": "Junior Data Scientist",
        "url": "https://linkedin.com/jobs/test-123",
        "snippet": (
            "We are looking for a junior data scientist to join our team. "
            "Requirements: Python, machine learning, pandas, scikit-learn. "
            "0-2 years experience. Location: Bangalore."
        ),
        "source": "linkedin"
    }

    result = _score_single(dummy_job, cv)
    print(f"\n  Raw Claude output:")
    print(json.dumps(result, indent=4))

    assert "score" in result, "Missing 'score' field"
    assert isinstance(result["score"], int), "'score' should be an integer"
    assert "reason" in result, "Missing 'reason' field"
    ok(f"Scorer works — score: {result['score']}/10")

except Exception as e:
    fail(f"Scorer error: {e}")

# ── All passed ────────────────────────────────────────────
print(f"\n{'='*50}")
print("  ALL TESTS PASSED — safe to run main.py")
print(f"{'='*50}\n")