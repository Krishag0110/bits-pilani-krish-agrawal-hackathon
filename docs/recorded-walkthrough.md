# SignalScope: ten-minute recorded walkthrough

Use this plan for the separate **Unlisted YouTube screen recording** requested by the submission guide. It is longer than the [five-minute live pitch](demo-script.md) so the reviewer can see startup, both source types, the signal contract, and portfolio calculations. Record the local application and public repository.

## Before recording

- Open the [public repository](https://github.com/Krishag0110/bits-pilani-krish-agrawal-hackathon), a terminal in the repository root, and a browser tab for `http://127.0.0.1:8000`. Keep the [architecture diagram](architecture.md) and [model card](model-card.md) ready.
- Check that port 8000 is free, then launch `python3 -m src.server` on camera at 0:45. The backend uses Python 3.9+ standard library only; no API key or package installation is required. Click **Reset demo** after the dashboard opens.
- Use **Refresh live feeds** only when network access is available. Live headlines and post counts change. In the latest verified current-code check, a `limit: 6` refresh added six Google News RSS headlines and five Bluesky posts; GDELT timed out, so news showed **Fallback** and social showed **OK**. Describe the status actually shown during recording.

## Timecoded screen and narration cues

| Time | On screen: clicks or commands | Narration cue |
| --- | --- | --- |
| **0:00–0:45** | Show the public repository and top of `README.md`; point to the deck and source/data folders. | “SignalScope converts public news headlines and social posts into traceable risk signals, then uses Module B to stress a fictional wholesale portfolio. This repository contains the code, sample data, assumptions, and slides.” |
| **0:45–1:30** | In the terminal, show `python3 -m src.server`, then run `curl http://127.0.0.1:8000/api/health`. Open the dashboard. | “The application runs locally with Python's standard library. The HTTP service exposes a JSON API and serves the dashboard.” |
| **1:30–2:20** | Click **Reset demo**. Show the summary cards and [architecture diagram](architecture.md). | “A reset loads labelled fictional replay records and a 12-position synthetic portfolio: five loans, four bonds, and three derivatives. No wholesale transaction file was supplied; the sample book is committed under `data/`.” |
| **2:20–3:35** | Click **Refresh live feeds**. Show **LIVE SOURCES** statuses; scroll to **Incoming signals** and toggle **News** and **Social**. Select a live item and, if available, open its source link. | “GDELT is the primary news list; Google News RSS supplies headline-only fallback. Bluesky provides public posts from two publisher accounts. Each signal retains provenance, a source URL, and a timestamp. A fallback or source error is shown rather than disguised as live success.” |
| **3:35–4:30** | Return to **Signal to scenario**. Point to sentiment, event class, impact, and **WHY THIS SIGNAL** for the selected record; briefly show the model card. | “A curated Naive Bayes baseline plus event cues classifies the text. A finance lexicon scores sentiment, and a severity rubric assigns impact from 1 to 10. Relative model confidence is not a calibrated probability.” |
| **4:30–5:25** | Under **Analyze text**, enter `Aster Manufacturing default risk eased after a strong profit recovery.` with entity `Aster Manufacturing` and **News article** selected; click **Generate signal**. | “This positive Credit Event scores sentiment `+0.908` and impact `7`. Since automatic stress needs impact above 7, no new scenario is triggered for this signal. Positive credit wording does not add issuer or sector deterioration.” |
| **5:25–6:30** | Click **Credit downgrade** under **TRY AN EXAMPLE**, then **Generate signal**. Show the selected manual signal. | “The tested Aster input reports a missed bond interest payment and downgrade risk. It becomes a **Credit Event**, sentiment `-0.937`, impact `10/10`. Source type and manual provenance remain visible; the high impact triggers stress automatically.” |
| **6:30–7:45** | Show **PORTFOLIO STRESS**, before/after bars, and shock chips. Point to **AUTO-TRIGGERED**. | “The fictional book falls from `$797.00m` to `$739.04m`: a `$57.96m` simulated loss, or `7.27%`. At impact 10 the scenario applies rates `+20 bp`, broad credit `+55 bp`, Industrials credit `+140 bp`, an Aster issuer haircut of `25%`, equities `-6%`, and FX `-2%`. The sector shock requires adverse credit language and a held obligor; the haircut additionally requires an affirmed payment failure or insolvency with negative sentiment.” |
| **7:45–8:40** | Scroll to **LOSS BY ASSET TYPE** and **Synthetic portfolio**. Point to loan, bond, and derivative rows and the base/stressed/P&L columns. | “Rounded losses are `$43.74m` in loans, `$12.52m` in bonds, and `$1.70m` in derivatives. Loans and bonds use first-order duration; derivatives use signed equity, rate, and FX sensitivities. Individual positions reconcile to the total.” |
| **8:40–9:25** | In the terminal, run the `GET /api/state` inspection command below and show the printed signal and stress values. Optionally run `python3 -m unittest discover -s tests -v`. | “The same structured signal and scenario are available to a downstream client as JSON. The latest loopback-enabled test run passed 26 tests; tests do not establish predictive accuracy.” |
| **9:25–10:00** | Show the README results/limitations and return to the dashboard. | “This is a transparent what-if and triage prototype. Headlines are incomplete, public feeds vary, and the shocks are illustrative. Before production use, we would evaluate on held-out labelled events and calibrate scenarios against an approved real portfolio.” |

For the API segment, use this short standard-library command after the **Credit downgrade** example so the newest signal and run refer to that case:

```bash
curl -s http://127.0.0.1:8000/api/state | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["signals"][0]; r=d["latest_run"]; print({k:s[k] for k in ("provenance","source","entity","sentiment_score","event_classification","impact_score")}); print({k:r[k] for k in ("before_value_usd_m","after_value_usd_m","loss_usd_m","loss_pct")})'
```

If a live source is unavailable during recording, keep its status visible, explain the failure, and continue with **Reset demo** and the manual Aster input. Label replay as replay. After uploading, set the YouTube video to **Unlisted**, verify the link in a private browser window, and insert it in the README's **Demo Video Link** field.
