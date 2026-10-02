"""No-key live adapters for news headlines and finance-related social posts.

GDELT exposes article titles and first-seen times, not complete article bodies.
Bluesky's public getAuthorFeed is unauthenticated. We pin two known publisher
profile DIDs and accept only their own posts, avoiding repost impersonation.
No failed request is silently replaced with demo or fabricated live material.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import re
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree


GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
GOOGLE_NEWS_ENDPOINT = "https://news.google.com/rss/search"
BLUESKY_ENDPOINT = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
# These DIDs were checked against each publisher's public bsky.app profile.
BLUESKY_ACTORS = {
    "financialtimes.com": "did:plc:5u54z2qgkq43dh2nzwzdbbhb",
    "bloomberg.com": "did:plc:uewxgchsjy4kmtu7dcxa77us",
}

# Author feeds include general-interest posts. A single broad token such as
# "investment" or a metaphorical "bond" is not enough to ingest a post.
STRONG_RELEVANCE = re.compile(
    r"\b(?:default\w*|bankrupt\w*|credit (?:rating|spread\w*|risk)|"
    r"interest rate\w*|rate hike\w*|central bank|bond yield\w*|stock market|"
    r"inflation|recession|sanction\w*|tariff\w*|merger\w*|acquisition|"
    r"takeover|debt crisis|oil prices?|currency crisis|earnings|gdp|"
    r"product launch|new product|war|geopolitical)\b",
    re.I,
)
FINANCIAL_TERMS = re.compile(
    r"\b(?:bank\w*|bond\w*|credit|loan\w*|stock\w*|share\w*|equities|"
    r"market\w*|invest\w*|econom\w*|recession|inflation|interest|rate\w*|"
    r"yield\w*|fed|ecb|central bank|sanction\w*|tariff\w*|trade|debt|"
    r"default\w*|bankrupt\w*|merger\w*|acqui\w*|commodit\w*|oil|"
    r"currency|dollar|euro|earnings|profit\w*|revenue|gdp|nasdaq|"
    r"s&p|shipping|war|geopolitical|regulat\w*|fraud|energy|price\w*)\b",
    re.I,
)
WEAK_CONTEXT = re.compile(r"(?:invest\w*|bond\w*|share\w*|trade|market\w*|price\w*)", re.I)


def _financially_relevant(text):
    if STRONG_RELEVANCE.search(text):
        return True
    matched_terms = {match.group().lower() for match in FINANCIAL_TERMS.finditer(text)}
    return len(matched_terms) >= 2 and any(
        not WEAK_CONTEXT.fullmatch(term) for term in matched_terms
    )


class SourceError(RuntimeError):
    """A live feed could not provide a usable response."""


@dataclass
class SourceBatch:
    items: list
    endpoint: str
    warning: str = ""


def _fetch_bytes(url, opener=None, timeout=6, accept="application/json"):
    request = Request(
        url,
        headers={
            "User-Agent": "SignalScope-Hackathon-Demo/1.0",
            "Accept": accept,
        },
    )
    open_request = opener or urlopen
    try:
        with open_request(request, timeout=timeout) as response:
            raw = response.read(2_000_001)
    except Exception as exc:
        raise SourceError("%s: %s" % (type(exc).__name__, exc)) from exc
    if len(raw) > 2_000_000:
        raise SourceError("Source response exceeded 2 MB")
    return raw


def _fetch_json(url, opener=None, timeout=6):
    raw = _fetch_bytes(url, opener, timeout)
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceError("Source returned invalid JSON") from exc


def _gdelt_time(value):
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (TypeError, ValueError):
        return ""


def fetch_gdelt(limit=12, opener=None, timeout=6):
    """Fetch GDELT DOC 2.0 ArticleList JSON and emit headline-only records."""
    limit = max(1, min(30, int(limit)))
    query = '(bankruptcy OR "credit rating" OR "interest rates" OR inflation OR sanctions OR merger)'
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "sort": "datedesc",
        "timespan": "24h",
        "maxrecords": str(limit),
    }
    payload = _fetch_json(GDELT_ENDPOINT + "?" + urlencode(params), opener, timeout)
    if not isinstance(payload, dict) or not isinstance(payload.get("articles"), list):
        raise SourceError("GDELT response lacked an articles list")
    items = []
    for article in payload["articles"]:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        if not title or not url.startswith(("https://", "http://")):
            continue
        seen_at = _gdelt_time(article.get("seendate"))
        items.append({
            "source": "news",
            "title": title[:300],
            "text": title[:12000],  # GDELT does not provide licensed full text.
            "url": url[:1000],
            "published_at": seen_at,
            "timestamp_basis": "gdelt_first_seen" if seen_at else "ingested_at",
        })
        if len(items) >= limit:
            break
    return SourceBatch(items=items, endpoint=GDELT_ENDPOINT)


def fetch_google_news(limit=12, opener=None, timeout=10):
    """Fallback: parse public Google News RSS headlines and channel pubDates."""
    limit = max(1, min(30, int(limit)))
    params = {
        "q": '"credit downgrade" OR "bank default" OR "rate hike" OR sanctions',
        "hl": "en-US", "gl": "US", "ceid": "US:en",
    }
    raw = _fetch_bytes(
        GOOGLE_NEWS_ENDPOINT + "?" + urlencode(params), opener, timeout,
        accept="application/rss+xml, application/xml;q=0.9",
    )
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise SourceError("Google News returned invalid RSS XML") from exc
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise SourceError("Google News response lacked an RSS channel")
    items = []
    for entry in channel.findall("item"):
        title = (entry.findtext("title") or "").strip()
        url = (entry.findtext("link") or "").strip()
        if not title or not url.startswith(("https://", "http://")):
            continue
        published_at = ""
        pub_date = (entry.findtext("pubDate") or "").strip()
        if pub_date:
            try:
                parsed = parsedate_to_datetime(pub_date)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                published_at = parsed.astimezone(timezone.utc).isoformat(
                    timespec="seconds"
                ).replace("+00:00", "Z")
            except (TypeError, ValueError):
                pass
        items.append({
            "source": "news",
            "title": title[:300],
            "text": title[:12000],  # RSS provides headlines, not full article bodies.
            "url": url[:1000],
            "published_at": published_at,
            "timestamp_basis": "rss_pubdate" if published_at else "ingested_at",
        })
        if len(items) >= limit:
            break
    return SourceBatch(items=items, endpoint=GOOGLE_NEWS_ENDPOINT)


def fetch_news(limit=12, opener=None, gdelt_timeout=3.5, rss_timeout=10):
    """Prefer GDELT; fall back to actual Google RSS on error or empty results."""
    try:
        primary = fetch_gdelt(limit, opener=opener, timeout=gdelt_timeout)
        if primary.items:
            return primary
        primary_problem = "GDELT returned no matching headlines"
    except SourceError as exc:
        primary_problem = "GDELT unavailable: %s" % exc
    try:
        fallback = fetch_google_news(limit, opener=opener, timeout=rss_timeout)
    except SourceError as exc:
        raise SourceError("%s; Google News RSS unavailable: %s" % (primary_problem, exc)) from exc
    fallback.warning = primary_problem + "; Google News RSS fallback active"
    return fallback


def _actor_feed(handle, did, limit, opener, timeout):
    params = {
        "actor": did,
        "limit": str(min(100, max(20, limit * 3))),
        "filter": "posts_no_replies",
        "includePins": "false",
    }
    payload = _fetch_json(BLUESKY_ENDPOINT + "?" + urlencode(params), opener, timeout)
    if not isinstance(payload, dict) or not isinstance(payload.get("feed"), list):
        raise SourceError("Bluesky %s response lacked a feed list" % handle)
    items = []
    for entry in payload["feed"]:
        if not isinstance(entry, dict):
            continue
        post = entry.get("post") or {}
        author = post.get("author") or {}
        if author.get("did") != did:
            continue  # A repost in an author feed is not the publisher's post.
        record = post.get("record") or {}
        text = record.get("text")
        uri = post.get("uri") or ""
        if not isinstance(text, str) or len(text.strip()) < 20 or not _financially_relevant(text):
            continue
        if not uri.startswith("at://") or "/app.bsky.feed.post/" not in uri:
            continue
        rkey = uri.rsplit("/", 1)[-1]
        display_handle = author.get("handle") or handle
        if not re.fullmatch(r"[a-zA-Z0-9.-]+", display_handle):
            display_handle = handle
        post_url = "https://bsky.app/profile/%s/post/%s" % (
            quote(display_handle, safe="."), quote(rkey, safe="")
        )
        clean_text = text.strip()
        items.append({
            "source": "social",
            "title": clean_text[:110] + ("…" if len(clean_text) > 110 else ""),
            "text": clean_text[:12000],
            "url": post_url,
            "published_at": record.get("createdAt") or post.get("indexedAt") or "",
            "timestamp_basis": "post_created_at",
        })
    return items


def fetch_bluesky(limit=12, opener=None, timeout=6):
    """Fetch finance-related original posts from two public publisher feeds."""
    limit = max(1, min(30, int(limit)))
    items = []
    errors = []
    with ThreadPoolExecutor(max_workers=len(BLUESKY_ACTORS)) as executor:
        futures = {
            executor.submit(_actor_feed, handle, did, limit, opener, timeout): handle
            for handle, did in BLUESKY_ACTORS.items()
        }
        for future in as_completed(futures):
            try:
                items.extend(future.result())
            except SourceError as exc:
                errors.append("%s: %s" % (futures[future], exc))
    if len(errors) == len(BLUESKY_ACTORS):
        raise SourceError("; ".join(errors))
    items.sort(key=lambda item: item["published_at"], reverse=True)
    deduplicated = []
    seen_urls = set()
    for item in items:
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        deduplicated.append(item)
        if len(deduplicated) >= limit:
            break
    return SourceBatch(
        items=deduplicated,
        endpoint=BLUESKY_ENDPOINT,
        warning="; ".join(errors),
    )
