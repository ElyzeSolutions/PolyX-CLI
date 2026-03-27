"""Test GraphQL client."""

import re

import pytest
from aioresponses import aioresponses

from polyx.client.graphql import GraphQLClient
from polyx.config import Config
from polyx.types import SearchResult


@pytest.mark.asyncio
async def test_graphql_search(monkeypatch):
    monkeypatch.setenv("AUTH_TOKEN", "test_auth")
    monkeypatch.setenv("CT0", "test_ct0")
    config = Config.load()
    client = GraphQLClient(config)

    # Mock query ID discovery
    mock_html = """
    <html><body>
    <script src="https://abs.twimg.com/responsive-web/client-web/main.12345.js"></script>
    </body></html>
    """

    mock_js = """
    {
        queryId: "mock_query_id",
        operationName: "SearchTimeline",
        operationType: "query",
        metadata: { featureSwitches: ["responsive_web_graphql_exclude_directive_enabled"] }
    }
    """

    mock_search_response = {
        "data": {
            "search_by_raw_query": {
                "search_timeline": {
                    "timeline": {
                        "instructions": [
                            {
                                "type": "TimelineAddEntries",
                                "entries": [
                                    {
                                        "entryId": "tweet-1",
                                        "content": {
                                            "entryType": "TimelineTimelineItem",
                                            "itemContent": {
                                                "itemType": "TimelineTweet",
                                                "tweet_results": {
                                                    "result": {
                                                        "rest_id": "1",
                                                        "core": {
                                                            "user_results": {
                                                                "result": {
                                                                    "legacy": {
                                                                        "screen_name": "user1",
                                                                        "name": "User One"
                                                                    }
                                                                }
                                                            }
                                                        },
                                                        "legacy": {
                                                            "full_text": "GraphQL tweet",
                                                            "created_at": "Wed Jan 01 00:00:00 +0000 2025",
                                                            "favorite_count": 10,
                                                            "retweet_count": 5
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        }
    }

    with aioresponses() as m:
        # Mock HTML discovery
        m.get("https://x.com/search?q=test&f=live", body=mock_html)
        m.get("https://abs.twimg.com/responsive-web/client-web/main.12345.js", body=mock_js)

        # Mock search API (switched to POST in implementation)
        m.post(re.compile(r".*SearchTimeline.*"), payload=mock_search_response)
        # Set mock query IDs manually to skip discovery in this test
        client._query_ids = {"SearchTimeline": "mock_query_id"}

        async with client:
            result = await client.search("bitcoin", limit=10)

        assert isinstance(result, SearchResult)
        assert len(result.tweets) == 1
        assert result.tweets[0].id == "1"
        assert result.tweets[0].text == "GraphQL tweet"
        assert result.client_type == "graphql"
