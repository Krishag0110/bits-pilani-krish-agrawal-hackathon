# SignalScope: five-minute live demonstration

This is the **live** demonstration plan for the case-study brief. The submission guide separately requests a recorded YouTube walkthrough; add its link to the root README when recorded.

## Prepare before the timer starts

1. Run `python3 -m src.server` from the repository root and open `http://127.0.0.1:8000`.
2. Verify the health endpoint at `http://127.0.0.1:8000/api/health` and keep the [architecture diagram](architecture.md) available.
3. Click **Reset demo** in the dashboard. This loads the bundled examples and synthetic portfolio; high-impact demo signals automatically receive stress runs. The same case can be shown even if a public feed is slow or has no relevant item.
4. Put the [presentation PDF](presentation.pdf) on its first slide. The deck should have no more than seven slides.

| Time | Show | Say |
| --- | --- | --- |
| **0:00–0:35** | Title and one-sentence problem statement. | “Risk teams read breaking news and social posts, but the information is unstructured. SignalScope turns public text into a structured, traceable risk signal and tests a defined portfolio scenario.” |
| **0:35–1:10** | Architecture diagram; point to GDELT, its Google News RSS fallback, Bluesky, risk engine, JSON API, and synthetic portfolio. | “The two adapters normalize different source types. The local engine assigns entity, sentiment, event, and impact; the stress module consumes that same signal. The system also has bundled replay data for a reproducible demo.” |
| **1:10–2:05** | Show the **Live sources** panel and **Incoming signals** feed. Click **Refresh live feeds** if network access is available; otherwise keep the labelled demo items in view. Point out **Fallback** if GDELT fails but RSS succeeds. | “This is the original headline or post and its provenance. The news path analyzes GDELT or fallback RSS headlines; the social path analyzes public Bluesky post text. Each source reports its own status.” |
| **2:05–3:00** | Under **Analyze text**, click **Credit downgrade**, then **Generate signal**. The example names Aster Manufacturing, a held obligor. | “Here is the machine-readable output: sentiment from `-1` to `1`, an event class, and impact from `1` to `10`. The source and matched text let us inspect why the engine flagged it. These are heuristic estimates, not a market-return prediction.” |
| **3:00–4:20** | Show the automatically triggered scenario. If desired, click **Rerun stress test**. Point to the Aster issuer haircut and Industrials spread shock chips, before/after values, **Loss by asset type**, and **Synthetic portfolio** table. | “This 12-position book is synthetic: five loans, four bonds, and three derivatives. A severe credit signal names a held obligor, so the stress adds a sector shock and issuer haircut on top of broad market shocks. The tested scenario moves this illustrative book from $797.00m to $739.04m, a $57.96m simulated loss.” |
| **4:20–5:00** | Summary/result and limitations slide. | “The practical use is faster triage and a transparent first-pass what-if view. The impact rubric and shocks are not calibrated to a bank’s real book; I would validate labels and calibrate scenarios before operational use.” |

## Questions to be ready for

The exact **Credit downgrade** quick example was tested as a manual news input: **Credit Event**, sentiment `-0.937`, impact `10/10`, followed automatically by the same `$57.96m` (`7.27%`) portfolio stress loss. The seeded Aster replay has a different text and sentiment (`-0.990`) but the same impact and shock result. Keep those two text scores distinct during the pitch.

- **Why these two sources?** GDELT offers public news article lists, with Google News RSS as a best-effort news fallback. Bluesky provides a distinct public social-post format. Both adapters can operate without a paid key for this prototype.
- **What happens if a feed is unavailable?** The adapter returns a source-specific error, and the committed replay examples still exercise the same normalization, NLP, and stress path.
- **What does the impact score mean?** It is an ordinal severity rubric that gates the illustrative scenario, not a probability, expected loss, or predicted percentage move.
- **How is the stress value calculated?** Loans and bonds use first-order rate and spread duration approximations; derivatives use signed equity, rate, and FX sensitivities. Shocks are event-specific and scaled by `impact / 10`.
- **How would you validate this?** Label a held-out set of multi-source events, measure entity/event/sentiment quality, and back-test or calibrate shocks against a real approved portfolio and historical outcomes.

## Recorded walkthrough TODO

The attached submission guidelines request a separate **10-minute screen recording** hosted as an Unlisted YouTube video. Record startup from the README commands, ingestion, one risk signal, the stress result, and the limitations; then put the verified public-viewable link in `README.md`.
