"""Application service connecting text analysis, live adapters and stress runs."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import threading
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid

from .model import RiskModel
from .portfolio import load_portfolio, run_stress
from .sources import fetch_bluesky, fetch_news
from .store import SQLiteStore


ROOT = Path(__file__).resolve().parent.parent
VALID_SOURCES = {"news", "social"}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_datetime(value, fallback):
    if not value:
        return fallback
    if not isinstance(value, str):
        raise ValueError("published_at must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("published_at must be an ISO-8601 string") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical_url(url):
    parsed = urlsplit(url)
    query = [
        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
    ]
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path.rstrip("/"), urlencode(sorted(query)), ""))


def _fingerprint(source, provenance, title, text, entity, url):
    key = (
        _canonical_url(url) if url else
        re.sub(r"\s+", " ", "%s %s %s" % (title, text, entity)).strip().casefold()
    )
    return hashlib.sha256((source + "|" + provenance + "|" + key).encode("utf-8")).hexdigest()


class RiskApplication:
    def __init__(self, db_path=None, seed_on_empty=True):
        self.portfolio = load_portfolio()
        self.model = RiskModel(portfolio_entities=[row["obligor"] for row in self.portfolio])
        self.store = SQLiteStore(db_path or ROOT / "data" / "signalscope.db")
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._generation = 0
        if seed_on_empty and not self.store.has_signals():
            self.reset_demo()

    def _make_signal(self, item, provenance):
        if not isinstance(item, dict):
            raise ValueError("Input must be a JSON object")
        source = item.get("source")
        if source not in VALID_SOURCES:
            raise ValueError("source must be 'news' or 'social'")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a nonempty string")
        text = text.strip()
        if len(text) > 12000:
            raise ValueError("text exceeds 12,000 characters")
        title = item.get("title") or ""
        if not isinstance(title, str) or len(title) > 300:
            raise ValueError("title must be at most 300 characters")
        title = title.strip() or text[:110]
        entity = item.get("entity") or ""
        if not isinstance(entity, str) or len(entity) > 120:
            raise ValueError("entity must be at most 120 characters")
        url = item.get("url") or ""
        if not isinstance(url, str) or len(url) > 1000:
            raise ValueError("url must be at most 1,000 characters")
        url = url.strip()
        if url:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("url must be an HTTP(S) URL")
        ingested_at = utc_now()
        published_at = _normalize_datetime(item.get("published_at"), ingested_at)
        basis = item.get("timestamp_basis") if provenance == "live" else None
        if basis not in {"gdelt_first_seen", "rss_pubdate", "post_created_at", "ingested_at"}:
            basis = "scenario_time" if provenance == "demo" else (
                "user_supplied" if item.get("published_at") else "ingested_at"
            )
        analysis = self.model.analyze(text, title=title, entity=entity)
        explanation = analysis["explanation"]
        if provenance == "live" and source == "news":
            if basis == "gdelt_first_seen":
                explanation += " GDELT supplied a headline and first-seen time; article body was not fetched."
            elif basis == "rss_pubdate":
                explanation += " Google News RSS supplied a headline and feed publication time; article body was not fetched."
            else:
                explanation += " The live feed supplied a headline only; article body was not fetched."
        signal = {
            "id": "sig_" + uuid.uuid4().hex[:12],
            "source": source,
            "provenance": provenance,
            "title": title,
            "text": text,
            "entity": analysis["entity"],
            "sentiment_score": analysis["sentiment_score"],
            "event_classification": analysis["event_classification"],
            "impact_score": analysis["impact_score"],
            "published_at": published_at,
            "ingested_at": ingested_at,
            "timestamp_basis": basis,
            "url": url,
            "evidence": analysis["evidence"],
            "explanation": explanation,
            "model_confidence": analysis["model_confidence"],
        }
        fingerprint = _fingerprint(source, provenance, title, text, signal["entity"], url)
        return signal, fingerprint

    def _ingest(self, item, provenance):
        signal, fingerprint = self._make_signal(item, provenance)
        stored, inserted = self.store.insert_signal(signal, fingerprint)
        if inserted:
            run = None
            if stored["impact_score"] > 7:
                run = run_stress(stored, self.portfolio)
                self.store.insert_run(run)
        else:
            run = self.store.latest_run_for_signal(stored["id"])
        return stored, run, inserted

    def analyze(self, item):
        with self._lock:
            signal, run, _ = self._ingest(item, "manual")
            state = self.state()
        return {"signal": signal, "run": run, "state": state}

    def reset_demo(self):
        examples = json.loads((ROOT / "data" / "demo_signals.json").read_text(encoding="utf-8"))
        with self._lock:
            self._generation += 1
            self.store.reset()
            now = datetime.now(timezone.utc)
            for example in examples:
                record = dict(example)
                minutes = int(record.pop("minutes_ago"))
                record["published_at"] = (
                    now - timedelta(minutes=minutes)
                ).isoformat(timespec="seconds").replace("+00:00", "Z")
                self._ingest(record, "demo")
            return self.state()

    def stress(self, signal_id):
        if not isinstance(signal_id, str) or not signal_id:
            raise ValueError("signal_id must be a nonempty string")
        with self._lock:
            signal = self.store.get_signal(signal_id)
            if signal is None:
                raise KeyError("Unknown signal_id")
            run = run_stress(signal, self.portfolio)
            self.store.insert_run(run)
            state = self.state()
        return {"run": run, "state": state}

    def refresh(self, limit=12):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 30:
            raise ValueError("limit must be an integer from 1 to 30")
        with self._refresh_lock:
            with self._lock:
                generation = self._generation
            added = []
            fetchers = {"news": fetch_news, "social": fetch_bluesky}
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(fetcher, limit): source for source, fetcher in fetchers.items()}
                for future in as_completed(futures):
                    source = futures[future]
                    attempted_at = utc_now()
                    try:
                        batch = future.result()
                    except Exception as exc:
                        with self._lock:
                            if generation == self._generation:
                                self.store.update_source_status(
                                    source, "error", attempted_at, 0, 0,
                                    error=str(exc),
                                )
                        continue
                    warning = batch.warning
                    added_from_source = 0
                    with self._lock:
                        if generation != self._generation:
                            continue  # A demo reset occurred during the network request.
                        for item in batch.items:
                            try:
                                stored, _, inserted = self._ingest(item, "live")
                            except ValueError as exc:
                                warning = (warning + "; " if warning else "") + str(exc)
                                continue
                            if inserted:
                                added.append(stored)
                                added_from_source += 1
                        self.store.update_source_status(
                            source, "degraded" if warning else "ok", attempted_at,
                            len(batch.items), added_from_source,
                            error=warning, endpoint=batch.endpoint,
                        )
            with self._lock:
                state = self.state()
        return {"added": added, "source_status": state["source_status"], "state": state}

    def state(self):
        with self._lock:
            signals = self.store.list_signals(limit=120)
            runs = self.store.list_runs(limit=40)
            statuses = self.store.source_status()
            counts = self.store.counts()
            baseline = round(sum(row["market_value_usd_m"] for row in self.portfolio), 2)
            latest = runs[0] if runs else None
            timestamps = [
                signals[0]["ingested_at"] if signals else "",
                latest["triggered_at"] if latest else "",
            ]
            timestamps.extend(status.get("last_attempt_at") or "" for status in statuses.values())
            metrics = {
                **counts,
                "portfolio_value_usd_m": baseline,
                "latest_stressed_value_usd_m": latest["after_value_usd_m"] if latest else None,
                "latest_loss_usd_m": latest["loss_usd_m"] if latest else None,
                "latest_loss_pct": latest["loss_pct"] if latest else None,
                "last_updated_at": max(timestamps) or utc_now(),
            }
            return {
                "signals": signals,
                "portfolio": [dict(row) for row in self.portfolio],
                "latest_run": latest,
                "runs": runs,
                "source_status": statuses,
                "metrics": metrics,
            }
