"""Transparent text models for event, sentiment, and impact extraction.

The event model is a Multinomial Naive Bayes classifier trained at startup on
the small, auditable corpus in data/training_examples.json. Explicit event cues
help short headlines, while sentiment and severity use finance-specific rules.
The outputs are screening signals, not calibrated probabilities or forecasts.
"""

from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
LABELS = (
    "Geopolitical",
    "Macroeconomic",
    "Credit Event",
    "Merger/Acquisition",
    "Product Launch",
    "Regulatory",
    "Operational",
    "Other",
)

STOP_WORDS = {
    "a", "about", "after", "all", "an", "and", "are", "as", "at", "be",
    "been", "by", "for", "from", "in", "into", "is", "it", "its", "of",
    "on", "or", "our", "the", "their", "this", "to", "with", "will",
    "fictional", "simulated", "scenario", "market", "post", "new",
}

WORD_ALIASES = {
    "defaults": "default", "defaulted": "default", "defaulting": "default",
    "misses": "missed", "missing": "missed", "payments": "payment",
    "downgrades": "downgrade", "downgraded": "downgrade",
    "upgrades": "upgrade", "upgraded": "upgrade",
    "sanction": "sanctions", "sanctioned": "sanctions",
    "acquires": "acquisition", "acquired": "acquisition", "acquire": "acquisition",
    "merges": "merger", "merged": "merger", "merging": "merger",
    "launches": "launch", "launched": "launch", "launching": "launch",
    "rates": "rate", "hikes": "hike", "raised": "raise", "raises": "raise",
    "cuts": "cut", "slumps": "slump", "surges": "surge",
    "breaches": "breach", "breached": "breach",
    "recalls": "recall", "recalled": "recall",
    "outages": "outage", "disrupts": "disrupt", "disrupted": "disrupt",
    "losses": "loss", "profits": "profit", "gains": "gain",
    "fines": "fine", "fined": "fine", "penalties": "penalty",
    "rules": "rule", "regulations": "regulation",
    "announces": "announce", "announced": "announce",
    "bonds": "bond", "loans": "loan", "lenders": "lender",
}

EVENT_CUES = {
    "Geopolitical": (
        ("sanctions", 1.5), ("trade embargo", 2.0), ("war", 1.8),
        ("military", 1.0), ("border conflict", 1.8), ("conflict", 1.2), ("tariff", 1.2),
        ("diplomatic", 1.0), ("invasion", 2.0), ("geopolitical", 1.6),
    ),
    "Macroeconomic": (
        ("inflation", 1.4), ("interest rate", 1.8), ("central bank", 1.8),
        ("rate hike", 1.6), ("recession", 1.7), ("unemployment", 1.0),
        ("gdp", 1.0), ("monetary policy", 1.5), ("federal reserve", 1.3),
        ("industrial output", 1.2), ("consumer prices", 1.2),
    ),
    "Credit Event": (
        ("default", 2.0), ("bankruptcy", 2.0), ("missed payment", 2.1),
        ("missed interest payment", 2.2), ("bond coupon", 1.5),
        ("credit rating", 1.4), ("downgrade", 1.2),
        ("debt restructuring", 1.7), ("insolvency", 2.0),
        ("credit spread", 1.3), ("creditor protection", 1.8),
    ),
    "Merger/Acquisition": (
        ("merger", 1.9), ("acquisition", 1.9), ("takeover", 1.9),
        ("buyout", 1.8), ("acquire", 1.4), ("deal talks", 1.3),
        ("purchase of", 1.1),
    ),
    "Product Launch": (
        ("product launch", 2.0), ("new product", 1.7), ("launch", 1.2),
        ("launched", 1.2), ("launches", 1.2), ("unveil", 1.3),
        ("unveiled", 1.3), ("rollout", 1.3), ("new platform", 1.4),
        ("commercial release", 1.4),
    ),
    "Regulatory": (
        ("regulator", 1.7), ("regulation", 1.7), ("antitrust", 1.6),
        ("compliance", 1.2), ("fine", 1.1), ("lawsuit", 1.2),
        ("enforcement", 1.5), ("capital requirement", 1.6),
    ),
    "Operational": (
        ("cyberattack", 1.9), ("data breach", 2.0), ("outage", 1.5),
        ("ransomware", 1.9), ("factory fire", 1.8), ("recall", 1.5),
        ("strike", 1.3), ("supply chain", 1.4),
    ),
}

SENTIMENT_PHRASES = (
    ("missed interest payment", -3.0), ("missed payment", -2.8),
    ("credit rating downgrade", -2.4), ("rating downgrade", -2.2),
    ("debt restructuring", -1.7), ("trade embargo", -1.6),
    ("inflation surge", -1.8), ("inflation surges", -1.8),
    ("inflation accelerates", -1.4), ("inflation rises", -1.2),
    ("default risk eased", 1.5), ("default fears ease", 1.5),
    ("data breach", -2.1), ("factory fire", -1.8),
    ("raises guidance", 2.1), ("raised guidance", 2.1),
    ("beats estimates", 2.0), ("rating upgrade", 2.2),
    ("credit rating upgrade", 2.4), ("strong demand", 1.5),
    ("profit growth", 1.7), ("stronger capital", 1.5),
)
SENTIMENT_WORDS = {
    "default": -2.9, "bankruptcy": -3.0, "insolvency": -2.8,
    "downgrade": -2.0, "loss": -1.4, "slump": -1.5,
    "recession": -2.2, "sanctions": -1.4, "lawsuit": -1.2,
    "layoff": -1.3, "fraud": -2.4, "breach": -1.7,
    "outage": -1.5, "disrupt": -1.2, "delay": -0.9,
    "weak": -1.2, "weaker": -1.2, "decline": -1.1,
    "fall": -1.1, "drops": -1.1, "missed": -1.1,
    "crisis": -2.0, "emergency": -1.1, "war": -2.0,
    "conflict": -1.2, "fire": -1.6, "recall": -1.5,
    "fine": -1.2, "penalty": -1.2, "hike": -0.5,
    "profit": 1.4, "upgrade": 2.0, "gain": 1.2,
    "growth": 1.2, "surge": 0.7, "strong": 1.1,
    "beat": 1.7, "approval": 1.2, "expand": 0.8,
    "record": 0.8, "improve": 1.2, "recovery": 1.3,
    "launch": 0.8, "demand": 0.7,
}

IMPACT_BASE = {
    "Geopolitical": 5, "Macroeconomic": 5, "Credit Event": 6,
    "Merger/Acquisition": 3, "Product Launch": 2, "Regulatory": 4,
    "Operational": 4, "Other": 2,
}
IMPACT_CUES = (
    ("bankruptcy", 3), ("default", 2), ("missed interest payment", 2),
    ("missed payment", 2), ("bond coupon", 1), ("insolvency", 2),
    ("systemic", 2), ("emergency", 2), ("war", 2),
    ("sanctions", 2), ("trade embargo", 1), ("recession", 2),
    ("inflation surge", 1), ("inflation surges", 1),
    ("fraud", 2), ("cyberattack", 2), ("data breach", 1),
    ("downgrade", 1),
)

KNOWN_ENTITIES = (
    "Federal Reserve", "European Central Bank", "Bank of England",
    "U.S. Treasury", "United States", "European Union", "China", "India",
)


def _words(text):
    return [WORD_ALIASES.get(word, word) for word in re.findall(r"[a-z][a-z0-9'-]*", text.lower())]


def _features(text):
    words = [word for word in _words(text) if word not in STOP_WORDS and len(word) > 2]
    features = list(words)
    features.extend("%s_%s" % (left, right) for left, right in zip(words, words[1:]))
    return features


def _contains_phrase(text, phrase):
    return re.search(r"(?<!\w)%s(?!\w)" % re.escape(phrase), text, re.I) is not None


def _is_negated(text, match_start):
    prefix = _words(text[max(0, match_start - 38):match_start])
    return any(word in {"no", "not", "never", "without", "avoids", "avoided"} for word in prefix[-4:])


def _first_match(text, phrase):
    return re.search(r"(?<!\w)%s(?!\w)" % re.escape(phrase), text, re.I)


class RiskModel:
    """Small auditable NLP pipeline. Relative class confidence is uncalibrated."""

    def __init__(self, training_path=None, portfolio_entities=()):
        path = Path(training_path) if training_path else ROOT / "data" / "training_examples.json"
        examples = json.loads(path.read_text(encoding="utf-8"))
        self.portfolio_entities = tuple(portfolio_entities)
        self.document_counts = Counter()
        self.token_counts = defaultdict(Counter)
        self.token_totals = Counter()
        vocabulary = set()
        for example in examples:
            label = example["label"]
            if label not in LABELS:
                raise ValueError("Unknown training label: %s" % label)
            features = _features(example["text"])
            self.document_counts[label] += 1
            self.token_counts[label].update(features)
            self.token_totals[label] += len(features)
            vocabulary.update(features)
        missing = set(LABELS) - set(self.document_counts)
        if missing:
            raise ValueError("Missing training labels: %s" % sorted(missing))
        self.vocabulary = vocabulary
        self.training_count = len(examples)

    def _classify(self, text):
        counts = Counter(feature for feature in _features(text) if feature in self.vocabulary)
        known_count = sum(counts.values())
        lower = text.lower()
        cue_hits = {}
        scores = {}
        for label in LABELS:
            denominator = self.token_totals[label] + len(self.vocabulary)
            log_score = math.log(self.document_counts[label] / self.training_count)
            for feature, count in counts.items():
                log_score += min(count, 2) * math.log(
                    (self.token_counts[label][feature] + 1) / denominator
                )
            # Length normalization keeps cue weights comparable for headlines
            # and longer social posts while preserving the learned NB ranking.
            log_score /= max(1.0, math.sqrt(known_count))
            matched = []
            for phrase, boost in EVENT_CUES.get(label, ()):
                if _contains_phrase(lower, phrase):
                    log_score += boost
                    matched.append(phrase)
            cue_hits[label] = matched
            scores[label] = log_score

        if known_count == 0 and not any(cue_hits.values()):
            return "Other", 0.25, []
        top_label = max(LABELS, key=lambda label: scores[label])
        maximum = max(scores.values())
        exponentials = {label: math.exp(scores[label] - maximum) for label in LABELS}
        confidence = exponentials[top_label] / sum(exponentials.values())
        if top_label != "Other" and not cue_hits[top_label] and (
            known_count < 2 or confidence < 0.50 or top_label == "Product Launch"
        ):
            return "Other", 0.25, []
        return top_label, round(confidence, 3), cue_hits[top_label][:4]

    def _sentiment(self, text):
        lower = text.lower()
        covered = [False] * len(text)
        hits = []
        total = 0.0
        for phrase, weight in sorted(SENTIMENT_PHRASES, key=lambda item: -len(item[0])):
            for match in re.finditer(r"(?<!\w)%s(?!\w)" % re.escape(phrase), lower):
                if any(covered[match.start():match.end()]):
                    continue
                if _is_negated(text, match.start()):
                    weight_here = -0.6 * weight
                else:
                    weight_here = weight
                total += weight_here
                hits.append((phrase, weight_here))
                covered[match.start():match.end()] = [True] * (match.end() - match.start())
        for match in re.finditer(r"[a-z][a-z0-9'-]*", lower):
            if any(covered[match.start():match.end()]):
                continue
            word = WORD_ALIASES.get(match.group(), match.group())
            weight = SENTIMENT_WORDS.get(word)
            if weight is None:
                continue
            weight_here = -0.6 * weight if _is_negated(text, match.start()) else weight
            total += weight_here
            hits.append((match.group(), weight_here))
        score = round(math.tanh(total / 3.5), 3)
        hits.sort(key=lambda item: abs(item[1]), reverse=True)
        return score, hits[:5]

    def _impact(self, text, event, sentiment):
        value = IMPACT_BASE[event]
        reasons = ["%s baseline %d" % (event, value)]
        lower = text.lower()
        # Keep the strongest two distinct severity cues; otherwise repetitions
        # in an article headline would inflate a 1-10 scale arbitrarily.
        matched = []
        for phrase, points in IMPACT_CUES:
            found = _first_match(lower, phrase)
            downplayed_default = False
            if found and phrase == "default":
                downplayed_default = bool(re.match(
                    r"\s+(?:risk|fears?)\s+(?:eased?|falls?|fades?|declines?|recedes?)\b",
                    lower[found.end():found.end() + 45],
                ))
            if found and not _is_negated(text, found.start()) and not downplayed_default:
                matched.append((phrase, points))
        matched.sort(key=lambda item: item[1], reverse=True)
        kept = []
        for phrase, points in matched:
            if any(phrase in earlier or earlier in phrase for earlier, _ in kept):
                continue
            kept.append((phrase, points))
            if len(kept) == 2:
                break
        for phrase, points in kept:
            value += points
            reasons.append("%s +%d" % (phrase, points))
        percentages = [float(number) for number in re.findall(r"\b(\d+(?:\.\d+)?)\s*%", text)]
        if percentages:
            maximum = max(percentages)
            if maximum >= 10:
                value += 2
                reasons.append("reported move >=10% +2")
            elif maximum >= 3:
                value += 1
                reasons.append("reported move >=3% +1")
        if re.search(r"\b(?:billion|bn)\b", lower):
            value += 1
            reasons.append("billion-scale amount +1")
        if abs(sentiment) >= 0.65:
            value += 1
            reasons.append("strong sentiment magnitude +1")
        if re.search(r"\b(?:rumou?r|unconfirmed|speculation)\b", lower):
            value -= 1
            reasons.append("unconfirmed report -1")
        return max(1, min(10, int(value))), reasons

    def _entity(self, text, supplied, event):
        if supplied and supplied.strip():
            return supplied.strip()
        candidates = []
        seen_spans = set()
        for name in self.portfolio_entities + KNOWN_ENTITIES:
            for match in re.finditer(r"(?<!\w)%s(?!\w)" % re.escape(name), text, re.I):
                span = (match.start(), match.end())
                if span not in seen_spans:
                    candidates.append((name, *span))
                    seen_spans.add(span)
        subject_pattern = re.compile(
            r"\b([A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,3})\s+"
            r"(?:announces?|announced|reports?|reported|misses?|missed|warns?|warned|"
            r"files?|filed|launches?|launched|raises?|raised|cuts?|cut|"
            r"acquires?|acquired|agrees?|agreed|faces?|faced|seeks?|sought|"
            r"unveils?|unveiled|defaults?|defaulted)\b",
        )
        for match in subject_pattern.finditer(text):
            name = match.group(1)
            span = match.span(1)
            if name.lower() in {"company", "bank", "government", "the company", "the bank"}:
                continue
            if span not in seen_spans:
                candidates.append((name, *span))
                seen_spans.add(span)
        if not candidates:
            return "Global market"

        clauses = [(match.start(), match.end()) for match in re.finditer(r"[^.!?;\n]+", text)]
        cue_positions = []
        for phrase, weight in EVENT_CUES.get(event, ()):
            cue_positions.extend(
                (match.start(), match.end(), weight)
                for match in re.finditer(r"(?<!\w)%s(?!\w)" % re.escape(phrase), text, re.I)
            )

        def clause_at(position):
            for index, (start, end) in enumerate(clauses):
                if start <= position < end:
                    return index
            return -1

        def rank(candidate):
            _, start, end = candidate
            clause = clause_at(start)
            nearby = [
                (cue_start, cue_end, weight) for cue_start, cue_end, weight in cue_positions
                if clause_at(cue_start) == clause
            ]
            proximity = max((
                weight * 50 - max(0, cue_start - end, start - cue_end)
                for cue_start, cue_end, weight in nearby
            ), default=0)
            return (max(0, proximity), -start)

        return max(candidates, key=rank)[0]

    def analyze(self, text, title="", entity=""):
        title = title.strip()
        text = text.strip()
        combined = (
            title if not text or text == title else
            text if title and text.startswith(title.rstrip("…")) else
            "%s. %s" % (title, text) if title else text
        )
        event, confidence, event_hits = self._classify(combined)
        sentiment, sentiment_hits = self._sentiment(combined)
        impact, impact_reasons = self._impact(combined, event, sentiment)
        evidence = ["event: %s" % hit for hit in event_hits]
        evidence.extend(
            "%s: %s" % ("positive" if weight > 0 else "negative", phrase)
            for phrase, weight in sentiment_hits
        )
        evidence = list(dict.fromkeys(evidence))
        if not evidence:
            evidence = ["No strong domain cue; classification is tentative"]
        direction = "positive" if sentiment > 0.1 else "negative" if sentiment < -0.1 else "neutral"
        explanation = (
            "Curated-corpus Naive Bayes and event cues classify this as %s "
            "(relative confidence %.2f). Finance language is %s (%.3f). "
            "Impact %d/10: %s."
            % (event, confidence, direction, sentiment, impact, "; ".join(impact_reasons))
        )
        return {
            "entity": self._entity(combined, entity, event),
            "sentiment_score": sentiment,
            "event_classification": event,
            "impact_score": impact,
            "evidence": evidence[:7],
            "explanation": explanation,
            "model_confidence": confidence,
        }
