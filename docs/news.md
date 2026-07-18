# X News API

PolyX exposes X's official [Search News endpoint](https://docs.x.com/x-api/news/search-news)
as a small typed client and CLI surface. Tweet search remains unchanged.

## CLI

```bash
polyx news "breaking technology news"
polyx news "gold Federal Reserve" --domain gold
polyx news "US election" --domain polymarket --max-results 25 --max-age-hours 12
polyx --json news "gold Federal Reserve" --domain gold
polyx --jsonl news "US election" --domain polymarket
polyx --markdown news "gold Federal Reserve" --domain gold
```

The official limits are enforced at both the CLI and client boundaries:

- `query`: 1–2,048 characters
- `max_results`: 1–100, default 10
- `max_age_hours`: 1–720, default 168

News search requires the official API v2 client and `X_BEARER_TOKEN`. Standalone
calls default to `--domain general`; integrations should declare `--domain gold`
or `--domain polymarket` to keep their streams independently routable. Domain is
an optional routing label, not a strategy requirement; custom integrations can
use their own 1-64 character lowercase label.

News uses the standard PolyX TTL cache. The cache key includes the domain,
query, result limit, and freshness window. Cache hits do not create ledger
charges. `--no-cache` forces a live request, refreshes the cache, and records the
returned resources in `polyx costs`.

Before any uncached request, PolyX checks `POLYX_DAILY_BUDGET`. Exhausted
budgets block the call before X is contacted, while cache hits remain readable.
Because the exact returned-story count is unknown before the request, PolyX
caps `max_results` to `floor(remaining budget / $0.005)`. If the remaining
budget cannot cover one story, the command fails clearly without making a paid
request. This local guard complements the authoritative spending limit in the
X Developer Console.

## Pricing and spend controls

X now uses [pay-per-use pricing](https://docs.x.com/x-api/getting-started/pricing):
credits are purchased upfront, deducted as requests consume resources, and can
be protected with a per-billing-cycle spending limit in the Developer Console.
X says resource prices can change and that the Console is the authoritative
source for current endpoint rates.

PolyX's general ledger uses the currently published rates of $0.005 per Post
read, $0.010 per User read, and $0.010 per Trends request.

The public pricing table currently lists the `news.new` webhook event at
**$0.005 per event**, but does not separately itemize a Search News story read.
PolyX therefore uses **$0.005 per returned News story** as its local working
estimate for `news/search`. Treat `polyx costs` as a safety estimate and compare
it with the Developer Console before high-frequency use. X also documents
24-hour UTC resource deduplication as a soft guarantee; PolyX's own cache avoids
depending on that guarantee.

## Python API

```python
from polyx.client.api_v2 import XAPIv2Client
from polyx.config import Config

async with XAPIv2Client(Config.load()) as client:
    result = await client.search_news(
        "gold Federal Reserve",
        max_results=25,
        max_age_hours=12,
    )

for story in result.stories:
    print(story.name, story.contexts.tickers, story.summary)
```

`NewsSearchResult` contains:

- `stories: list[NewsStory]`
- `query`, `total_results`, and `max_age_hours`
- partial RFC 7807 API errors, when X returns usable data with warnings
- caller-supplied routing `domain` and local `cached` state

Each `NewsStory` includes its ID, headline, summary, hook, category, update time,
keywords, disclaimer, structured entity/finance/sports context, and clustered
Post IDs. Parsing accepts both current documented field names (`id`,
`updated_at`) and the legacy response aliases still shown in X examples
(`rest_id`, `last_updated_at_ms`). Unknown fields are ignored and malformed
optional collections degrade to empty typed values.

## Integration guidance

Consumers such as Polybot should treat stories as candidate evidence, not as
trade instructions. Route by strategy before scoring:

- Polymarket can search the market question, named entities, and resolution
  criteria.
- Gold strategies can use a narrow query set such as `gold`, `XAUUSD`, central
  banks, real yields, inflation, dollar, and geopolitical risk.

Keep those query sets and downstream queues separate. The structured tickers,
topics, organizations, people, and Post IDs make that separation deterministic
without changing PolyX's generic news client. JSON retains the result envelope;
every JSONL record repeats `source`, `domain`, `query`, `client_type`, freshness,
cache state, and API errors so independently consumed lines remain safely
routable.
