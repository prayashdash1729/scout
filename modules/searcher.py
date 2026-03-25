"""
Module 1: Search job boards using Tavily.
Returns a list of raw job dicts for the scorer to evaluate.
"""

from tavily import TavilyClient
from config import TAVILY_API_KEY, CANDIDATE, JOB_SEARCH_QUERIES
from memory.db import job_exists

client = TavilyClient(api_key=TAVILY_API_KEY)

def search_jobs() -> list[dict]:
    """
    Run all query templates across all roles × cities.
    Returns deduplicated list of raw job postings not yet in DB.
    """
    raw_results = []
    seen_urls   = set()

    for role in CANDIDATE["target_roles"]:
        for city in CANDIDATE["target_cities"]:
            for query_template in JOB_SEARCH_QUERIES:
                query = query_template.format(role=role, city=city)
                print(f"[Search] {query}")

                try:
                    results = client.search(
                        query=query,
                        max_results=5,
                        search_depth="advanced",  # more thorough
                        include_answer=False,
                    )

                    for r in results.get("results", []):
                        url = r.get("url", "")

                        # Skip if already seen in this run or in DB
                        if url in seen_urls or job_exists(url):
                            continue

                        seen_urls.add(url)
                        raw_results.append({
                            "title":   r.get("title", ""),
                            "url":     url,
                            "snippet": r.get("content", ""),
                            "source":  _detect_source(url),
                            "role_query": role,
                            "city_query": city,
                        })

                except Exception as e:
                    print(f"[Search] Error on query '{query}': {e}")
                    continue

    print(f"[Search] Found {len(raw_results)} new listings.")
    return raw_results


def _detect_source(url: str) -> str:
    """Infer which job board a URL came from."""
    if "linkedin.com"   in url: return "linkedin"
    if "naukri.com"     in url: return "naukri"
    if "instahyre.com"  in url: return "instahyre"
    if "wellfound.com"  in url: return "wellfound"
    if "indeed.com"     in url: return "indeed"
    return "other"