"""Test output formats."""

import json

from polyx.output.formats import get_formatter
from polyx.types import NewsAPIError, NewsContexts, NewsPost, NewsSearchResult, NewsStory


def test_terminal_formatter(sample_search_result):
    formatter = get_formatter("terminal")
    output = formatter.format_search(sample_search_result)

    # Check for specific elements in terminal output
    assert "Bitcoin moon pump rally" in output
    assert "@bull1" in output
    assert "likes" in output.lower()


def test_json_formatter(sample_search_result):
    formatter = get_formatter("json")
    output = formatter.format_search(sample_search_result)

    data = json.loads(output)
    assert data["query"] == "bitcoin"
    assert len(data["tweets"]) == 5
    assert data["tweets"][0]["id"] == "1"


def test_jsonl_formatter(sample_search_result):
    formatter = get_formatter("jsonl")
    output = formatter.format_search(sample_search_result)

    lines = output.strip().split("\n")
    assert len(lines) == 5

    data = json.loads(lines[0])
    assert data["id"] == "1"


def test_csv_formatter(sample_search_result):
    formatter = get_formatter("csv")
    output = formatter.format_search(sample_search_result)

    lines = output.strip().split("\n")
    assert len(lines) == 6  # 1 header + 5 tweets
    assert "id,username,name,text" in lines[0]
    assert "1," in lines[1]


def test_markdown_formatter(sample_search_result):
    formatter = get_formatter("markdown")
    output = formatter.format_search(sample_search_result)

    assert "# Search: bitcoin" in output
    assert "### 1. @bull1" in output


def _sample_news_result():
    return NewsSearchResult(
        stories=[
            NewsStory(
                id="news-1",
                name="Gold rises on rate outlook",
                summary="Gold advanced as yields fell.",
                category="News",
                updated_at="2026-07-18T08:30:00Z",
                contexts=NewsContexts(tickers=["XAUUSD"], topics=["Gold"]),
                cluster_posts=[NewsPost(post_id="post-1")],
            )
        ],
        query="gold",
        total_results=1,
        max_age_hours=24,
        domain="gold",
    )


def test_news_terminal_and_markdown_formatters():
    result = _sample_news_result()

    terminal = get_formatter("terminal").format_news(result)
    markdown = get_formatter("markdown").format_news(result)

    assert "Gold rises on rate outlook" in terminal
    assert "Tickers: XAUUSD" in terminal
    assert "https://x.com/i/status/post-1" in terminal
    assert "# X News: gold" in markdown


def test_news_json_and_jsonl_formatters():
    result = _sample_news_result()

    json_data = json.loads(get_formatter("json").format_news(result))
    jsonl_data = json.loads(get_formatter("jsonl").format_news(result))

    assert json_data["stories"][0]["contexts"]["finance"]["tickers"] == ["XAUUSD"]
    assert jsonl_data["id"] == "news-1"
    assert jsonl_data["source"] == "polyx"
    assert jsonl_data["query"] == "gold"
    assert jsonl_data["domain"] == "gold"
    assert jsonl_data["client_type"] == "api_v2"
    assert jsonl_data["type"] == "news_story"


def test_news_terminal_surfaces_api_error_without_stories():
    result = NewsSearchResult(
        query="gold",
        errors=[NewsAPIError(title="Forbidden", detail="News access is not enabled")],
    )

    output = get_formatter("terminal").format_news(result)

    assert "News access is not enabled" in output


def test_news_jsonl_preserves_errors_without_stories():
    result = NewsSearchResult(
        query="election",
        domain="polymarket",
        errors=[NewsAPIError(title="Partial", detail="Context unavailable")],
    )

    output = json.loads(get_formatter("jsonl").format_news(result))

    assert output["type"] == "news_result"
    assert output["domain"] == "polymarket"
    assert output["errors"][0]["detail"] == "Context unavailable"


def test_empty_news_csv_emits_header():
    result = NewsSearchResult(query="gold", domain="gold")

    output = get_formatter("csv").format_news(result)

    assert output == "source,domain,query,id,name,category,updated_at,summary,hook,tickers,topics"
