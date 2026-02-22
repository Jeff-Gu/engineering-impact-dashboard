"""GitHub API client for fetching repository data."""

import os
from datetime import datetime, timedelta
from typing import Optional

import requests
import streamlit as st

GITHUB_API_BASE = "https://api.github.com"
REPO_OWNER = "PostHog"
REPO_NAME = "posthog"


def get_github_token() -> Optional[str]:
    """Get GitHub token from Streamlit secrets or environment."""
    try:
        return st.secrets.get("GITHUB_TOKEN")
    except Exception:
        return os.environ.get("GITHUB_TOKEN")


def get_headers() -> dict:
    """Build request headers with optional authentication."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = get_github_token()
    if token:
        headers["Authorization"] = f"token {token}"
    return headers


def paginate_request(url: str, params: dict, since_date: datetime) -> list:
    """Fetch all pages of results, stopping when we pass the since_date."""
    all_items = []
    headers = get_headers()
    params["per_page"] = 100
    page = 1

    while True:
        params["page"] = page
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        items = response.json()

        if not items:
            break

        for item in items:
            # Check date based on item type
            date_field = item.get("merged_at") or item.get("closed_at") or item.get("created_at")
            if date_field:
                item_date = datetime.fromisoformat(date_field.replace("Z", "+00:00"))
                if item_date.replace(tzinfo=None) < since_date:
                    return all_items
            all_items.append(item)

        # Check if there are more pages
        if len(items) < 100:
            break
        page += 1

    return all_items


@st.cache_data(ttl=3600, show_spinner="Fetching merged PRs...")
def fetch_merged_prs(days: int = 90) -> list:
    """Fetch all PRs merged in the last N days."""
    since_date = datetime.utcnow() - timedelta(days=days)
    url = f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/pulls"
    params = {
        "state": "closed",
        "sort": "updated",
        "direction": "desc",
    }

    all_prs = paginate_request(url, params, since_date)

    # Filter to only merged PRs within the date range
    merged_prs = []
    for pr in all_prs:
        if pr.get("merged_at"):
            merged_date = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
            if merged_date.replace(tzinfo=None) >= since_date:
                merged_prs.append(pr)

    return merged_prs


@st.cache_data(ttl=3600, show_spinner="Fetching closed issues...")
def fetch_closed_issues(days: int = 90) -> list:
    """Fetch all issues closed in the last N days."""
    since_date = datetime.utcnow() - timedelta(days=days)
    url = f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/issues"
    params = {
        "state": "closed",
        "sort": "updated",
        "direction": "desc",
        "since": since_date.isoformat() + "Z",
    }

    all_issues = paginate_request(url, params, since_date)

    # Filter out pull requests (GitHub API includes PRs in issues endpoint)
    issues = [issue for issue in all_issues if "pull_request" not in issue]

    # Filter to issues closed within the date range
    closed_issues = []
    for issue in issues:
        if issue.get("closed_at"):
            closed_date = datetime.fromisoformat(issue["closed_at"].replace("Z", "+00:00"))
            if closed_date.replace(tzinfo=None) >= since_date:
                closed_issues.append(issue)

    return closed_issues


@st.cache_data(ttl=3600, show_spinner="Fetching PR details...")
def fetch_pr_details(pr_number: int) -> dict:
    """Fetch detailed PR info including additions/deletions."""
    url = f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}"
    headers = get_headers()
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


@st.cache_data(ttl=3600, show_spinner="Fetching reviews...")
def fetch_pr_reviews(pr_number: int) -> list:
    """Fetch all reviews for a PR."""
    url = f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}/reviews"
    headers = get_headers()
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_all_reviews_for_prs(prs: list, progress_callback=None) -> dict:
    """Fetch reviews for all PRs, returning a dict keyed by PR number."""
    reviews_by_pr = {}
    total = len(prs)

    for i, pr in enumerate(prs):
        pr_number = pr["number"]
        try:
            reviews_by_pr[pr_number] = fetch_pr_reviews(pr_number)
        except requests.RequestException:
            reviews_by_pr[pr_number] = []

        if progress_callback:
            progress_callback((i + 1) / total)

    return reviews_by_pr


def fetch_pr_sizes(prs: list, progress_callback=None) -> dict:
    """Fetch size details for all PRs."""
    sizes = {}
    total = len(prs)

    for i, pr in enumerate(prs):
        pr_number = pr["number"]
        try:
            details = fetch_pr_details(pr_number)
            sizes[pr_number] = {
                "additions": details.get("additions", 0),
                "deletions": details.get("deletions", 0),
            }
        except requests.RequestException:
            sizes[pr_number] = {"additions": 0, "deletions": 0}

        if progress_callback:
            progress_callback((i + 1) / total)

    return sizes
