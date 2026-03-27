"""Test output formats."""

import json

from polyx.output.formats import get_formatter


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
