# SignalScope model card and stress assumptions

## Intended use

SignalScope is a hackathon prototype for **event triage and scenario exploration**. It converts public news headlines and public social posts into a compact risk signal for a named company or event. Module B then uses that signal to select an adverse scenario for a synthetic wholesale-banking portfolio. An analyst should be able to trace every displayed score back to text and a source.

The output is **not** a probability of default, a return forecast, an expected-loss model, or an instruction to trade. The event impact number is an ordinal severity estimate for this demonstration. A 10 is more severe under the rubric than a 5; it is not twice the expected financial loss.

## Inputs and outputs

| Item | Meaning |
| --- | --- |
| News input | GDELT DOC 2.0 ArticleList headline and metadata, or Google News RSS headline on fallback; full article text is not fetched. |
| Social input | Public Bluesky post text and metadata from selected author feeds. |
| Replay input | Bundled example text used to reproduce the demonstration without a live feed. |
| Sentiment score | Text sentiment on a `-1` to `1` scale, where negative values are adverse language, `0` is neutral, and positive values are favorable language. |
| Event classification | The classifier's best-fitting event category; it reflects the text, not external verification that an event occurred. |
| Impact score | Ordinal `1` to `10` estimate from a documented severity rubric. |
| Model confidence | Relative score for the selected event label; uncalibrated and not a likelihood of real-world correctness. |
| Evidence | Source identity or URL, timestamp when available, and text used to calculate the signal. |

## Text-analysis method

The event classifier is an in-repository **Multinomial Naive Bayes** baseline trained on 80 curated, labelled event phrases: 10 examples each for Geopolitical, Macroeconomic, Credit Event, Merger/Acquisition, Product Launch, Regulatory, Operational, and Other. It uses word and adjacent-word features with add-one smoothing. Explicit domain cue boosts help short headlines. Low-evidence, no-cue predictions abstain to **Other** rather than forcing a specific class; a G7 oil-reserve-release headline is a tested example. Its displayed `model_confidence` is a relative score from the classifier and cue weights, **not** a calibrated probability that the label is true.

Sentiment sums an original finance-oriented word and phrase lexicon, with a short preceding negation check, and maps the sum through a bounded function to `-1`–`1`. When no entity is supplied, extraction favors the company mention nearest event language, but the method cannot reliably assign sentiment separately to every company in a multi-entity story. This design runs with Python's standard library and has no remote model call or paid API dependency.

The impact rubric starts with an event-class baseline, adds at most two distinct severity phrase weights, then adjusts for a reported percentage move, a billion-scale amount, strong sentiment magnitude, or rumor language. Negated severity phrases do not add points. The result is clamped to `1`–`10`:

| Event class | Starting score |
| --- | ---: |
| Credit Event | 6 |
| Geopolitical, Macroeconomic | 5 |
| Regulatory, Operational | 4 |
| Merger/Acquisition | 3 |
| Product Launch, Other | 2 |

In the regression example “Aster Manufacturing default risk eased after a strong profit recovery,” the engine outputs a positive Credit Event with impact `7`; automatic stress requires an impact above `7`.

The curated examples support the prototype and its deterministic behavior. They are **not** an independent, representative test set. No classification accuracy, sentiment correlation with returns, or impact calibration statistic is claimed. The code and unit tests should be inspected for exact tokenization, labels, term weights, and scoring thresholds.

## Portfolio stress method

The portfolio is wholly synthetic: **five loans, four bonds, and three derivatives**. Event categories map to a fixed adverse shock vector of interest-rate, credit-spread, equity, and FX moves. The engine scales that vector by `impact_score / 10` **regardless of sentiment**. An **adverse** Credit Event naming an exact held obligor also adds a sector spread shock of up to 140 basis points. An affirmed payment failure or insolvency with negative sentiment adds an issuer haircut of up to 25%; both extras scale with impact. Positive credit signals receive neither add-on. Negated payment-failure language cannot by itself trigger the haircut, and a sector shock still requires adverse sentiment. A manual stress run retains the broad adverse sensitivity.

For loans and bonds, the engine uses first-order interest-rate and credit-spread duration losses and then applies any issuer haircut. For derivatives, P&L is the sum of signed equity delta times the equity return, signed rate PV01 times the rate change in basis points, and FX delta times the FX return. Derivative mark-to-market values can become negative. The dashboard reports each position's base value, stressed value, and change before summing the portfolio.

These are simple, local mark-to-market approximations. They omit nonlinear derivative effects, changing default likelihood, liquidity, wrong-way risk, netting agreements, hedging dynamics, and feedback between markets. No historical simulation or external market data calibrates the shocks. The stress result answers *“What happens to this illustrative book under these defined shocks?”* and does not estimate what will happen after an actual event.

## Important limitations

- A headline can omit qualifications in the article body; a short post can be rumor, opinion, satire, or a quotation. Both can produce a confident-sounding label from incomplete evidence.
- The social adapter monitors original posts from two publisher accounts and requires a strong finance/risk phrase or two distinct relevant terms including a non-ambiguous anchor. It does not measure the broader public's views on Bluesky or other social networks.
- Company-name ambiguity, negation, conditional language, and multi-company stories can cause wrong target attribution or polarity.
- Public feeds may omit posts, change response formats, rate-limit clients, or return no relevant items. GDELT [documents DOC API rate limiting](https://blog.gdeltproject.org/ukraine-api-rate-limiting-web-ngrams-3-0/). Google News RSS is a best-effort fallback without a guaranteed developer API contract. The [Bluesky author-feed schema](https://github.com/bluesky-social/atproto/blob/main/lexicons/app/bsky/feed/getAuthorFeed.json) specifies the public endpoint, but service availability is external to this project.
- In a current-code networked refresh on 2 October 2026, GDELT timed out during TLS connection. The fallback added six real Google News RSS headlines, and Bluesky added five posts after relevance filtering. News reported a degraded fallback status and GDELT warning; social reported OK. Live item counts vary, and local replay cannot guarantee remote availability at presentation time.
- Curated training phrases and a finance lexicon may miss new event language and perform differently across sectors, languages, or regions.
- Multiple reports about one event can overstate apparent corroboration unless duplicates are removed or grouped. The source timestamp is publication or indexing time, not necessarily the time the event occurred.
- The impact rubric and scenario shocks are illustrative. They should not be used to size a real position or set a financial institution's capital.

## Evaluation status

The repository test suite checks deterministic text processing, signal ranges, stress arithmetic, and HTTP routes. With localhost sockets permitted, it reported `Ran 26 tests ... OK`. The default shell sandbox reported `Ran 24 tests ... OK (skipped=1)` because `APITests.setUpClass` could not bind localhost; its two methods were not counted. These tests do not establish real-world predictive validity. Numerical examples in the presentation and README come from tested runs on the bundled synthetic portfolio, with the input, signal, scenario, and units shown together.

## Data and reproducibility

Only fictional portfolio records, curated examples, and public source text are used. The case materials did not include a wholesale transaction file; the suggested consumer banking and fraud datasets would not supply suitable wholesale position sensitivities. The team therefore created the committed sample positions and assumptions in [`data/`](../data/). No confidential S&P Global, Crisil, or client transaction data is included. The local replay route enables a repeatable run; live refresh results naturally depend on source availability and time.
