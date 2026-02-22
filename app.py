"""Engineering Impact Dashboard - Main Streamlit App."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from github_client import (
    fetch_merged_prs,
    fetch_closed_issues,
    fetch_all_reviews_for_prs,
    fetch_pr_sizes,
    get_github_token,
)
from metrics import calculate_engineer_metrics, get_top_engineers

st.set_page_config(
    page_title="Engineering Impact Dashboard",
    page_icon="🏆",
    layout="wide",
)

st.title("🏆 Top 5 Most Impactful Engineers (90 days)")
st.caption("Analyzing PostHog/posthog repository")

# Check for GitHub token
if not get_github_token():
    st.warning(
        "No GitHub token found. API rate limits will be restrictive. "
        "Set GITHUB_TOKEN in .streamlit/secrets.toml or as an environment variable."
    )

# Sidebar with metric explanation
with st.sidebar:
    st.header("📊 Impact Score Formula")
    st.markdown("""
    ```
    Impact Score =
      (PRs × Size Weight)
    + (Issues Closed × 2)
    + (Reviews Given)
    × (1.2 if avg review < 24h
       1.0 if avg review <= 72h
       0.8 if avg review > 72h)
    ```

    **PR Size Weights:**
    - Small (<100 lines): 1×
    - Medium (100-500): 2×
    - Large (>500): 3×
    """)

    st.divider()
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()


@st.cache_data(ttl=3600, show_spinner=False)
def load_all_data():
    """Load and process all GitHub data."""
    # Fetch base data
    prs = fetch_merged_prs(days=90)
    issues = fetch_closed_issues(days=90)

    return prs, issues


# Load data
with st.spinner("Loading GitHub data..."):
    try:
        prs, issues = load_all_data()
    except Exception as e:
        st.error(f"Failed to fetch data from GitHub: {e}")
        st.stop()

st.info(f"Found {len(prs)} merged PRs and {len(issues)} closed issues in the last 90 days")

# Fetch detailed data with progress
col1, col2 = st.columns(2)

with col1:
    pr_progress = st.progress(0, text="Fetching PR sizes...")
    pr_sizes = fetch_pr_sizes(prs, progress_callback=lambda p: pr_progress.progress(p, text=f"Fetching PR sizes... {int(p*100)}%"))
    pr_progress.empty()

with col2:
    review_progress = st.progress(0, text="Fetching reviews...")
    reviews = fetch_all_reviews_for_prs(prs, progress_callback=lambda p: review_progress.progress(p, text=f"Fetching reviews... {int(p*100)}%"))
    review_progress.empty()

# Calculate metrics
df = calculate_engineer_metrics(prs, issues, reviews, pr_sizes)
top_5 = get_top_engineers(df, n=5)

if top_5.empty:
    st.warning("No engineer data found for the selected period.")
    st.stop()

# Main bar chart
st.subheader("Impact Score Leaderboard")
fig_bar = px.bar(
    top_5,
    x="engineer",
    y="impact_score",
    color="impact_score",
    color_continuous_scale="viridis",
    labels={"engineer": "Engineer", "impact_score": "Impact Score"},
)
fig_bar.update_layout(
    showlegend=False,
    coloraxis_showscale=False,
    xaxis_title="",
    yaxis_title="Impact Score",
)
st.plotly_chart(fig_bar, use_container_width=True)

# Engineer cards and breakdown
st.subheader("Top 5 Engineers Breakdown")

for i, (_, row) in enumerate(top_5.iterrows()):
    with st.expander(f"#{i+1} {row['engineer']} - Score: {row['impact_score']}", expanded=(i == 0)):
        col1, col2 = st.columns([1, 2])

        with col1:
            st.metric("PRs Merged", row["prs_merged"])
            st.caption(f"S: {row['prs_small']} | M: {row['prs_medium']} | L: {row['prs_large']}")
            st.metric("Issues Closed", row["issues_closed"])
            st.metric("Reviews Given", row["reviews_given"])
            if row["avg_review_hours"]:
                st.metric("Avg Review Time", f"{row['avg_review_hours']}h")
                multiplier = row["review_multiplier"]
                if multiplier > 1.0:
                    st.success("Fast reviewer (+20%)")
                elif multiplier < 1.0:
                    st.warning("Slow reviewer (-20%)")

        with col2:
            # Score breakdown pie chart
            breakdown_data = {
                "Component": ["PR Score", "Issue Score", "Review Score"],
                "Points": [row["pr_score"], row["issue_score"], row["reviews_given"]],
            }
            fig_pie = px.pie(
                breakdown_data,
                values="Points",
                names="Component",
                title="Score Breakdown",
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig_pie, use_container_width=True)

# Full leaderboard table
st.subheader("Full Leaderboard")
with st.expander("View all engineers"):
    display_df = df[["engineer", "impact_score", "prs_merged", "issues_closed", "reviews_given"]].copy()
    display_df.columns = ["Engineer", "Impact Score", "PRs Merged", "Issues Closed", "Reviews Given"]
    display_df.index = pd.RangeIndex(start=1, stop=len(display_df) + 1)
    display_df.index.name = "Rank"
    st.dataframe(display_df, use_container_width=True)

# Footer
st.divider()
st.caption("Data refreshes hourly. Click 'Refresh Data' in the sidebar to force update.")
