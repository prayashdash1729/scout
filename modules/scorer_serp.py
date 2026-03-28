"""
Module 1: Search job boards using SerpAPI (Google Search).
Returns a list of raw job dicts for the scorer to evaluate.
"""

import os
import requests
from config import CANDIDATE, JOB_SEARCH_QUERIES
from memory.db import job_exists

SERP_API_KEY = os.getenv("SERPAPI_API_KEY")
SERP_URL     = "https://serpapi.com/search"

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

                results = _google_search(query)
                for r in results:
                    url = r.get("url", "")
                    if not url or url in seen_urls or job_exists(url):
                        continue
                    seen_urls.add(url)
                    raw_results.append({
                        "title":      r.get("title", ""),
                        "url":        url,
                        "snippet":    r.get("snippet", ""),
                        "source":     _detect_source(url),
                        "role_query": role,
                        "city_query": city,
                    })

    print(f"[Search] Found {len(raw_results)} new listings.")
    return raw_results


def _google_search(query: str, num: int = 10) -> list[dict]:
    """
    Call SerpAPI and return cleaned organic results.
    Falls back to empty list on any error so the agent keeps running.
    """
    try:
        params = {
            "q":       query,
            "api_key": SERP_API_KEY,
            "engine":  "google",
            "num":     num,
            "hl":      "en",
            "gl":      "in",   # India — better localised results
        }
        resp = requests.get(SERP_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # SerpAPI returns organic_results for regular search
        results = []
        for item in data.get("organic_results", []):
            results.append({
                "title":   item.get("title", ""),
                "url":     item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })
        return results

    except requests.exceptions.Timeout:
        print(f"[Search] Timeout on query: {query}")
        return []
    except Exception as e:
        print(f"[Search] Error: {e}")
        return []


def _detect_source(url: str) -> str:
    if "linkedin.com"  in url: return "linkedin"
    if "naukri.com"    in url: return "naukri"
    if "instahyre.com" in url: return "instahyre"
    if "wellfound.com" in url: return "wellfound"
    if "indeed.com"    in url: return "indeed"
    return "other"