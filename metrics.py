"""Impact score calculations for engineers."""

from collections import defaultdict
from datetime import datetime
from typing import TypedDict

import pandas as pd


class EngineerStats(TypedDict):
    prs_merged: int
    prs_small: int
    prs_medium: int
    prs_large: int
    pr_score: int
    issues_closed: int
    reviews_given: int
    review_times: list[float]


def create_default_stats() -> EngineerStats:
    return {
        "prs_merged": 0,
        "prs_small": 0,
        "prs_medium": 0,
        "prs_large": 0,
        "pr_score": 0,
        "issues_closed": 0,
        "reviews_given": 0,
        "review_times": [],
    }


def classify_pr_size(additions: int, deletions: int) -> tuple[str, int]:
    """Classify PR size and return (label, weight)."""
    total_lines = additions + deletions
    if total_lines < 100:
        return "Small", 1
    elif total_lines <= 500:
        return "Medium", 2
    else:
        return "Large", 3


def calculate_review_turnaround(pr_created_at: str, review_submitted_at: str) -> float:
    """Calculate hours between PR creation and review submission."""
    pr_time = datetime.fromisoformat(pr_created_at.replace("Z", "+00:00"))
    review_time = datetime.fromisoformat(review_submitted_at.replace("Z", "+00:00"))
    delta = review_time - pr_time
    return delta.total_seconds() / 3600


def _collect_pr_stats(
    merged_prs: list,
    pr_sizes: dict,
    stats: dict[str, EngineerStats],
) -> None:
    """Credit each PR author based on the size-weighted score of their merged PRs."""
    for pr in merged_prs:
        author = pr["user"]["login"]
        size_info = pr_sizes.get(pr["number"], {"additions": 0, "deletions": 0})
        size_label, weight = classify_pr_size(size_info["additions"], size_info["deletions"])

        stats[author]["prs_merged"] += 1
        stats[author][f"prs_{size_label.lower()}"] += 1
        stats[author]["pr_score"] += weight


def _collect_issue_stats(
    closed_issues: list,
    stats: dict[str, EngineerStats],
) -> None:
    """Credit the assignees of each closed issue (falls back to issue creator)."""
    for issue in closed_issues:
        assignees = issue.get("assignees", [])
        recipients = [a["login"] for a in assignees] if assignees else [issue["user"]["login"]]
        for login in recipients:
            stats[login]["issues_closed"] += 1


def _collect_review_stats(
    merged_prs: list,
    reviews_by_pr: dict,
    stats: dict[str, EngineerStats],
) -> None:
    """Credit reviewers for each review given, excluding self-reviews."""
    for pr in merged_prs:
        author = pr["user"]["login"]
        for review in reviews_by_pr.get(pr["number"], []):
            reviewer = review.get("user", {}).get("login")
            if not reviewer or reviewer == author:
                continue

            stats[reviewer]["reviews_given"] += 1

            if review.get("submitted_at"):
                hours = calculate_review_turnaround(pr["created_at"], review["submitted_at"])
                stats[reviewer]["review_times"].append(hours)


def _compute_impact_score(stats: EngineerStats) -> dict:
    """Derive final scores and metadata from a single engineer's raw stats."""
    pr_score = stats["pr_score"]
    issue_score = stats["issues_closed"] * 2
    review_score = stats["reviews_given"]
    base_score = pr_score + issue_score + review_score

    review_times = stats["review_times"]
    avg_review_hours = sum(review_times) / len(review_times) if review_times else None

    if avg_review_hours is None:
        review_multiplier = 1.0       # no reviews — neutral
    elif avg_review_hours < 24:
        review_multiplier = 1.2       # fast reviewer bonus
    elif avg_review_hours <= 72:
        review_multiplier = 1.0       # acceptable — neutral
    else:
        review_multiplier = 0.8       # slow reviewer penalty

    return {
        "impact_score": round(base_score * review_multiplier, 1),
        "pr_score": pr_score,
        "issue_score": issue_score,
        "avg_review_hours": round(avg_review_hours, 1) if avg_review_hours is not None else None,
        "review_multiplier": review_multiplier,
    }


def calculate_engineer_metrics(
    merged_prs: list,
    closed_issues: list,
    reviews_by_pr: dict,
    pr_sizes: dict,
) -> pd.DataFrame:
    """Aggregate GitHub activity into a ranked engineer impact DataFrame."""
    stats: dict[str, EngineerStats] = defaultdict(create_default_stats)

    _collect_pr_stats(merged_prs, pr_sizes, stats)
    _collect_issue_stats(closed_issues, stats)
    _collect_review_stats(merged_prs, reviews_by_pr, stats)

    rows = [
        {
            "engineer": engineer,
            "prs_merged": s["prs_merged"],
            "prs_small": s["prs_small"],
            "prs_medium": s["prs_medium"],
            "prs_large": s["prs_large"],
            "issues_closed": s["issues_closed"],
            "reviews_given": s["reviews_given"],
            **_compute_impact_score(s),
        }
        for engineer, s in stats.items()
        if not engineer.endswith("[bot]")
    ]

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("impact_score", ascending=False).reset_index(drop=True)
    return df


def get_top_engineers(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Return the top N engineers by impact score."""
    return df.head(n)
