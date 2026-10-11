# SignalScope: two-minute application demo script

This is a word-for-word script for a concise application recording. It demonstrates the full text → signal → stress path in about two minutes. The case brief caps the live demonstration at five minutes; the attached submission guide separately lists a ten-minute recorded walkthrough, so check the required recording length before final submission.

## Set up before recording

1. In the repository root, run **python3 -m src.server** and open **http://127.0.0.1:8000** on the same computer.
2. Click **Reset demo**. This loads labelled fictional replay records and the synthetic portfolio.
3. Put the browser at the top of the dashboard. Keep the **Credit downgrade** quick example ready. Live feed refresh is optional; do not wait for a network call during the timed recording.

## Record these five beats

### 0:00–0:20 — Purpose

**On screen:** Dashboard title and summary cards.

> Financial risk teams need to turn fast-moving text into decisions. SignalScope reads public news headlines and social posts, produces a traceable risk signal, and applies it to a synthetic wholesale portfolio. I have reset the app to a clearly labelled replay so you can reproduce this result.

### 0:20–0:40 — Two input sources

**On screen:** **Live sources** and **Incoming signals**; briefly select **News** and **Social**.

> The feed has labelled examples of news and social text. Live refresh uses GDELT headlines, with Google News RSS as a fallback, and public Bluesky posts. Each source reports its status. Every signal carries provenance, sentiment, event type and impact; the same data is available through a JSON API.

### 0:40–1:05 — Generate a signal

**On screen:** Under **Analyze text**, click **Credit downgrade**, then **Generate signal**. Point to the selected signal and its explanation.

> I will use the Credit downgrade example. This fictional Aster Manufacturing item says it missed a bond interest payment. The engine classifies it as a Credit Event, with sentiment negative zero point nine three seven and impact ten out of ten. The original text and explanation stay visible for review.

### 1:05–1:40 — Stress the portfolio

**On screen:** **Portfolio stress** before/after bars, shock chips, and **Loss by asset type**.

> Impact above seven automatically runs Module B. It applies a defined adverse scenario to twelve synthetic loans, bonds and derivatives. You can see rate, spread, equity and FX shocks, plus an Aster issuer haircut. The book moves from seven hundred ninety-seven million dollars to seven hundred thirty-nine point zero four million: a simulated loss of fifty-seven point nine six million, or seven point two seven percent. The asset breakdown shows where that loss sits.

### 1:40–2:00 — Close

**On screen:** Synthetic portfolio table, then return to the risk signal.

> This is a transparent what-if for triage, not a market forecast. Analysts can inspect the source, risk signal and portfolio effect in one place. The book and shocks are illustrative and would need validation against approved real data before operational use.

## Recording checks

- The **Credit downgrade** quick example is a manual, fictional input. Keep its provenance visible; do not describe it as a live news item.
- Its tested output is **Credit Event**, sentiment **−0.937**, impact **10/10**. The deterministic scenario is **$797.00m → $739.04m**, a **$57.96m** simulated loss (**7.27%**).
- If you upload the recording to YouTube, set it to **Unlisted**, test the link in a private window, and replace the video-link TODO in the [README](../README.md).
- For a longer live pitch and Q&A cues, use the [five-minute demonstration script](demo-script.md).
