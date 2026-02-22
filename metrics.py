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


def calculate_engineer_metrics(
    merged_prs: list,
    closed_issues: list,
    reviews_by_pr: dict,
    pr_sizes: dict,
) -> pd.DataFrame:
    """Calculate impact metrics for all engineers."""
    engineer_stats: dict[str, EngineerStats] = defaultdict(create_default_stats)

    # Process merged PRs
    for pr in merged_prs:
        author = pr["user"]["login"]
        pr_number = pr["number"]
        size_info = pr_sizes.get(pr_number, {"additions": 0, "deletions": 0})
        size_label, weight = classify_pr_size(
            size_info["additions"], size_info["deletions"]
        )

        engineer_stats[author]["prs_merged"] += 1
        engineer_stats[author][f"prs_{size_label.lower()}"] += 1
        engineer_stats[author]["pr_score"] += weight

    # Process closed issues
    for issue in closed_issues:
        # Issues may be closed by the assignee or the closer
        assignees = issue.get("assignees", [])
        if assignees:
            for assignee in assignees:
                engineer_stats[assignee["login"]]["issues_closed"] += 1
        elif issue.get("user"):
            # Fall back to issue creator if no assignee
            engineer_stats[issue["user"]["login"]]["issues_closed"] += 1

    # Process reviews
    for pr in merged_prs:
        pr_number = pr["number"]
        pr_created = pr["created_at"]
        reviews = reviews_by_pr.get(pr_number, [])

        for review in reviews:
            reviewer = review.get("user", {}).get("login")
            if not reviewer:
                continue

            # Don't count self-reviews
            if reviewer == pr["user"]["login"]:
                continue

            engineer_stats[reviewer]["reviews_given"] += 1

            # Track review turnaround time
            if review.get("submitted_at"):
                turnaround = calculate_review_turnaround(pr_created, review["submitted_at"])
                engineer_stats[reviewer]["review_times"].append(turnaround)

    # Calculate final scores
    results = []
    for engineer, stats in engineer_stats.items():
        # Base score components
        pr_score = stats["pr_score"]
        issue_score = stats["issues_closed"] * 2
        review_score = stats["reviews_given"]

        base_score = pr_score + issue_score + review_score

        # Review turnaround bonus
        review_times = stats["review_times"]
        avg_review_time = sum(review_times) / len(review_times) if review_times else float("inf")
        turnaround_bonus = 1.1 if avg_review_time < 24 else 1.0

        impact_score = base_score * turnaround_bonus

        results.append({
            "engineer": engineer,
            "impact_score": round(impact_score, 1),
            "prs_merged": stats["prs_merged"],
            "prs_small": stats["prs_small"],
            "prs_medium": stats["prs_medium"],
            "prs_large": stats["prs_large"],
            "pr_score": pr_score,
            "issues_closed": stats["issues_closed"],
            "issue_score": issue_score,
            "reviews_given": stats["reviews_given"],
            "avg_review_hours": round(avg_review_time, 1) if review_times else None,
            "has_turnaround_bonus": turnaround_bonus > 1,
        })

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values("impact_score", ascending=False).reset_index(drop=True)

    return df


def get_top_engineers(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Return the top N engineers by impact score."""
    return df.head(n)
