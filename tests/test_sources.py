import json
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
import unittest

from src.sources import (
    BLUESKY_ACTORS, SourceError, fetch_bluesky, fetch_gdelt,
    fetch_google_news, fetch_news,
)


class Response:
    def __init__(self, payload, raw=False):
        self.body = payload if raw else json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.body[:size]


class SourceTests(unittest.TestCase):
    def test_gdelt_article_headline_and_seen_time(self):
        def opener(request, timeout):
            self.assertIn("api.gdeltproject.org", request.full_url)
            self.assertEqual(parse_qs(urlsplit(request.full_url).query)["format"], ["json"])
            return Response({"articles": [
                {"title": "Bank faces credit rating downgrade", "url": "https://example.org/story",
                 "seendate": "20261002T100000Z"},
                {"title": "", "url": "https://example.org/empty"},
            ]})

        batch = fetch_gdelt(limit=3, opener=opener)
        self.assertEqual(len(batch.items), 1)
        self.assertEqual(batch.items[0]["source"], "news")
        self.assertEqual(batch.items[0]["text"], batch.items[0]["title"])
        self.assertEqual(batch.items[0]["published_at"], "2026-10-02T10:00:00Z")
        self.assertEqual(batch.items[0]["timestamp_basis"], "gdelt_first_seen")

    def test_google_news_rss_headline_link_and_pubdate(self):
        rss = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><title>Google News</title>
          <item><title>Bank faces credit downgrade - Publisher</title>
          <link>https://news.google.com/rss/articles/abc</link>
          <pubDate>Fri, 02 Oct 2026 12:15:00 GMT</pubDate></item>
          <item><title>No link</title><pubDate>Fri, 02 Oct 2026 12:16:00 GMT</pubDate></item>
        </channel></rss>"""

        def opener(request, timeout):
            self.assertIn("news.google.com/rss/search", request.full_url)
            self.assertEqual(
                parse_qs(urlsplit(request.full_url).query)["q"],
                ['"credit downgrade" OR "bank default" OR "rate hike" OR sanctions'],
            )
            return Response(rss, raw=True)

        batch = fetch_google_news(limit=2, opener=opener)
        self.assertEqual(len(batch.items), 1)
        self.assertEqual(batch.items[0]["published_at"], "2026-10-02T12:15:00Z")
        self.assertEqual(batch.items[0]["timestamp_basis"], "rss_pubdate")
        self.assertEqual(batch.items[0]["source"], "news")

    def test_gdelt_failure_uses_real_rss_and_reports_degradation(self):
        rss = b"""<rss version="2.0"><channel><item>
            <title>Credit risk widens</title><link>https://news.google.com/rss/articles/xyz</link>
            <pubDate>Fri, 02 Oct 2026 12:15:00 GMT</pubDate>
        </item></channel></rss>"""

        def opener(request, timeout):
            if "gdeltproject.org" in request.full_url:
                raise URLError("simulated timeout")
            return Response(rss, raw=True)

        batch = fetch_news(limit=2, opener=opener)
        self.assertEqual(len(batch.items), 1)
        self.assertIn("news.google.com", batch.endpoint)
        self.assertIn("GDELT unavailable", batch.warning)
        self.assertIn("fallback active", batch.warning)

    def test_bluesky_keeps_only_relevant_original_posts(self):
        dids = BLUESKY_ACTORS

        def post(did, handle, rkey, text):
            return {"post": {
                "author": {"did": did, "handle": handle},
                "uri": "at://%s/app.bsky.feed.post/%s" % (did, rkey),
                "record": {"text": text, "createdAt": "2026-10-02T11:00:00.000Z"},
            }}

        def opener(request, timeout):
            actor = parse_qs(urlsplit(request.full_url).query)["actor"][0]
            if actor == dids["financialtimes.com"]:
                return Response({"feed": [
                    post(actor, "financialtimes.com", "one", "Bank bond yields rise after a credit downgrade."),
                    post(actor, "financialtimes.com", "two", "A lovely photograph from the city garden."),
                    post(actor, "financialtimes.com", "five", "Our bond with the city grew stronger after the concert."),
                    post(actor, "financialtimes.com", "six", "Investment in fine dining is all about patience."),
                    post(actor, "financialtimes.com", "seven", "The Man City crisis pits a bid for UK investment against football fans, threatening that bond."),
                    post("did:plc:someoneelse", "untrusted.example", "three", "Markets plunge today."),
                ]})
            return Response({"feed": [
                post(actor, "bloomberg.com", "four", "Oil prices fall as energy demand slows."),
            ]})

        batch = fetch_bluesky(limit=5, opener=opener)
        self.assertEqual(len(batch.items), 2)
        self.assertEqual({item["source"] for item in batch.items}, {"social"})
        self.assertTrue(all(item["url"].startswith("https://bsky.app/profile/") for item in batch.items))
        self.assertTrue(all(item["published_at"] for item in batch.items))

    def test_one_actor_failure_is_visible_without_fabricated_fallback(self):
        def opener(request, timeout):
            actor = parse_qs(urlsplit(request.full_url).query)["actor"][0]
            if actor == BLUESKY_ACTORS["financialtimes.com"]:
                raise URLError("simulated outage")
            return Response({"feed": []})

        batch = fetch_bluesky(limit=2, opener=opener)
        self.assertEqual(batch.items, [])
        self.assertIn("financialtimes.com", batch.warning)

        def fail_all(request, timeout):
            raise URLError("simulated outage")

        with self.assertRaises(SourceError):
            fetch_bluesky(limit=2, opener=fail_all)


if __name__ == "__main__":
    unittest.main()
