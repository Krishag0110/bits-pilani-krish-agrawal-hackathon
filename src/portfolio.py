"""Synthetic wholesale portfolio and deterministic event stress scenarios."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid


ROOT = Path(__file__).resolve().parent.parent

# Base adverse scenarios at impact 10. Every factor is scaled by impact / 10.
# Credit events use modest market spillover plus concentrated sector/issuer risk.
SCENARIOS = {
    "Geopolitical": {
        "name": "Cross-border disruption",
        "rationale": "Global funding and risk appetite shock from geopolitical disruption.",
        "rates_bps": 80.0, "credit_spreads_bps": 160.0,
        "equities_pct": -14.0, "fx_pct": -8.0,
    },
    "Macroeconomic": {
        "name": "Inflation and policy repricing",
        "rationale": "Rates, credit, equity, and currency shocks from a broad macro event.",
        "rates_bps": 150.0, "credit_spreads_bps": 110.0,
        "equities_pct": -16.0, "fx_pct": -6.0,
    },
    "Credit Event": {
        "name": "Obligor credit deterioration",
        "rationale": "Small market spillover; larger shocks to a held issuer and its sector when identified.",
        "rates_bps": 20.0, "credit_spreads_bps": 55.0,
        "equities_pct": -6.0, "fx_pct": -2.0,
    },
    "Merger/Acquisition": {
        "name": "Deal risk repricing",
        "rationale": "Adverse sensitivity case around financing and execution risk.",
        "rates_bps": 30.0, "credit_spreads_bps": 75.0,
        "equities_pct": -8.0, "fx_pct": -2.0,
    },
    "Product Launch": {
        "name": "Commercial execution risk",
        "rationale": "Adverse sensitivity case for product execution uncertainty.",
        "rates_bps": 20.0, "credit_spreads_bps": 45.0,
        "equities_pct": -5.0, "fx_pct": -2.0,
    },
    "Regulatory": {
        "name": "Regulatory repricing",
        "rationale": "Compliance and funding shock across market risk factors.",
        "rates_bps": 60.0, "credit_spreads_bps": 110.0,
        "equities_pct": -10.0, "fx_pct": -4.0,
    },
    "Operational": {
        "name": "Operational disruption",
        "rationale": "Funding and risk appetite shock after an operational incident.",
        "rates_bps": 30.0, "credit_spreads_bps": 85.0,
        "equities_pct": -8.0, "fx_pct": -3.0,
    },
    "Other": {
        "name": "Generic adverse sensitivity",
        "rationale": "Broad illustrative sensitivity case where the event category is uncertain.",
        "rates_bps": 70.0, "credit_spreads_bps": 95.0,
        "equities_pct": -9.0, "fx_pct": -4.0,
    },
}

# These indicate an observed payment failure or insolvency, rather than a
# discussion of default risk, a warning, or an avoided default.
SEVERE_CREDIT_PATTERNS = tuple(re.compile(pattern, re.I) for pattern in (
    r"\bdefaulted\b",
    r"\bdefaults? on\b",
    r"\b(?:is|are|was|were|enters?|entered|falls?|fell|declared) (?:in )?default\b",
    r"\b(?:files?|filed|entered|enters?) (?:for |into )?bankruptcy\b",
    r"\b(?:is|was|becomes?|became|declared) insolvent\b",
    r"\b(?:missed|misses) (?:an? |the )?(?:bond )?(?:interest )?payment\b",
    r"\b(?:missed|misses) (?:a |the )?bond coupon\b",
    r"\b(?:fails?|failed) to (?:pay|repay|service)\b",
))
NEGATORS = {
    "no", "not", "never", "without", "avoid", "avoids", "avoided",
    "avert", "averts", "averted", "prevent", "prevents", "prevented",
    "escape", "escapes", "escaped", "denies", "denied",
}


def load_portfolio(path=None):
    """Load and minimally validate the committed fictional portfolio."""
    data_path = Path(path) if path else ROOT / "data" / "portfolio.json"
    rows = json.loads(data_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("Portfolio must be a nonempty list")
    identifiers = set()
    required = {
        "id", "obligor", "asset_type", "sector", "region", "notional_usd_m",
        "market_value_usd_m", "rate_duration_years", "spread_duration_years",
        "equity_delta_usd_m", "rate_pv01_usd_m_per_bp", "fx_delta_usd_m",
    }
    for row in rows:
        if not required.issubset(row):
            raise ValueError("Portfolio row lacks fields: %s" % row.get("id", "?"))
        if row["id"] in identifiers:
            raise ValueError("Duplicate portfolio id: %s" % row["id"])
        identifiers.add(row["id"])
        if row["asset_type"] not in {"loan", "bond", "derivative"}:
            raise ValueError("Unknown asset type: %s" % row["asset_type"])
        if row["notional_usd_m"] < 0:
            raise ValueError("Negative notional: %s" % row["id"])
    return rows


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _held_obligor(signal_entity, positions):
    target = signal_entity.strip().casefold()
    for position in positions:
        if position["asset_type"] in {"loan", "bond"} and position["obligor"].casefold() == target:
            return position["obligor"], position["sector"]
    return None, None


def _affirmed_severe_credit(text):
    """Find a default/payment-failure cue that is not locally negated."""
    for pattern in SEVERE_CREDIT_PATTERNS:
        for match in pattern.finditer(text):
            prefix = text[max(0, match.start() - 80):match.start()].lower()
            prefix = re.split(r"[.!?;\n]", prefix)[-1]
            recent_words = re.findall(r"[a-z]+", prefix)[-8:]
            if not any(word in NEGATORS for word in recent_words):
                return True
    return False


def run_stress(signal, positions, triggered_at=None):
    """Mark a fictional book to one adverse, event-specific first-order scenario.

    Rates and credit spreads are in basis points; equity and FX changes are
    percent returns. A pay-fixed swap has positive signed rate PV01 and thus
    offsets part of a rising-rate loss. Negative derivative MTM is allowed.
    """
    event = signal["event_classification"]
    if event not in SCENARIOS:
        event = "Other"
    impact = int(signal["impact_score"])
    if not 1 <= impact <= 10:
        raise ValueError("impact_score must be in [1, 10]")
    scale = impact / 10.0
    base = SCENARIOS[event]
    shocks = {
        key: round(base[key] * scale, 2)
        for key in ("rates_bps", "credit_spreads_bps", "equities_pct", "fx_pct")
    }
    affected_obligor, affected_sector = _held_obligor(signal.get("entity", ""), positions)
    severe_credit = event == "Credit Event" and _affirmed_severe_credit(
        "%s. %s" % (signal.get("title", ""), signal.get("text", ""))
    )
    sentiment = signal.get("sentiment_score")
    adverse_credit = event == "Credit Event" and (
        float(sentiment) < -0.15 if sentiment is not None else severe_credit
    )
    shocks["sector_credit_spreads_bps"] = round(
        140.0 * scale if adverse_credit and affected_sector else 0.0, 2
    )
    shocks["issuer_haircut_pct"] = round(
        25.0 * scale if severe_credit and adverse_credit and affected_obligor else 0.0, 2
    )
    scenario = {
        "name": "Credit-market downside sensitivity" if event == "Credit Event" and not adverse_credit else base["name"],
        "rationale": (
            "Adverse what-if for a non-adverse credit headline; no issuer or sector deterioration is assumed."
            if event == "Credit Event" and not adverse_credit else base["rationale"]
        ),
        "scale": round(scale, 2),
        "shocks": shocks,
        "affected_obligor": affected_obligor,
        "affected_sector": affected_sector,
    }
    assumptions = [
        "All positions and values are fictional USD millions; scenarios are adverse sensitivities, not forecasts.",
        "Base event shocks are scaled by impact_score / 10 regardless of sentiment.",
        "Loans and bonds: value after market shock = max(0, value x [1 - rate duration x rate move - spread duration x spread move]); moves are decimal rates.",
        "Derivatives: P&L = equity delta x equity return + signed rate PV01 x rate change in bp + FX delta x FX return; negative derivative MTM is possible.",
        "Adverse Credit Event: 140 bp sector spread shock for a matched held obligor; an affirmed payment failure plus negative sentiment adds a 25% issuer haircut, both scaled by impact.",
        "Durations and deltas are fixed; convexity, correlations, recovery dynamics, and liquidity effects are omitted.",
    ]
    results = []
    for position in positions:
        before = float(position["market_value_usd_m"])
        if position["asset_type"] in {"loan", "bond"}:
            sector_bp = shocks["sector_credit_spreads_bps"] if position["sector"] == affected_sector else 0.0
            spread_bp = shocks["credit_spreads_bps"] + sector_bp
            market_factor = 1.0 - (
                float(position["rate_duration_years"]) * shocks["rates_bps"] / 10000.0
                + float(position["spread_duration_years"]) * spread_bp / 10000.0
            )
            after = before * max(0.0, market_factor)
            issuer_haircut = shocks["issuer_haircut_pct"] if position["obligor"] == affected_obligor else 0.0
            after *= 1.0 - issuer_haircut / 100.0
            driver = "Rates +%.0f bp; credit +%.0f bp" % (shocks["rates_bps"], spread_bp)
            if issuer_haircut:
                driver += "; issuer haircut %.1f%%" % issuer_haircut
        else:
            change = (
                float(position["equity_delta_usd_m"]) * shocks["equities_pct"] / 100.0
                + float(position["rate_pv01_usd_m_per_bp"]) * shocks["rates_bps"]
                + float(position["fx_delta_usd_m"]) * shocks["fx_pct"] / 100.0
            )
            after = before + change
            driver = "Equity %.1f%%; rates +%.0f bp; FX %.1f%%" % (
                shocks["equities_pct"], shocks["rates_bps"], shocks["fx_pct"]
            )
        after_rounded = round(after, 2)
        results.append({
            "id": position["id"],
            "obligor": position["obligor"],
            "asset_type": position["asset_type"],
            "before_value_usd_m": round(before, 2),
            "after_value_usd_m": after_rounded,
            "pnl_usd_m": round(after_rounded - round(before, 2), 2),
            "driver": driver,
        })

    before_total = round(sum(row["before_value_usd_m"] for row in results), 2)
    after_total = round(sum(row["after_value_usd_m"] for row in results), 2)
    pnl = round(after_total - before_total, 2)
    loss = round(max(0.0, -pnl), 2)
    return {
        "id": "run_" + uuid.uuid4().hex[:12],
        "signal_id": signal["id"],
        "event_classification": event,
        "impact_score": impact,
        "entity": signal.get("entity", "Global market"),
        "triggered_at": triggered_at or _utc_now(),
        "scenario": scenario,
        "assumptions": assumptions,
        "before_value_usd_m": before_total,
        "after_value_usd_m": after_total,
        "pnl_usd_m": pnl,
        "loss_usd_m": loss,
        "loss_pct": round(100.0 * loss / before_total, 2) if before_total else 0.0,
        "positions": results,
    }
