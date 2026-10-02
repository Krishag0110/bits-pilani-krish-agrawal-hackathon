# Included data

- `training_examples.json`: hand-written, fictional short-text examples used to train the in-repository event classifier. These are not a benchmark or external dataset.
- `portfolio.json`: 12 fully synthetic wholesale positions (five loans, four bonds, three derivatives). Amounts are USD millions. Sensitivities and values are illustrative, not based on CRISIL or client positions.
- `demo_signals.json`: fictional replay inputs. Every stored replay signal is labelled `provenance: "demo"`; no replay item is presented as live news or a real social post.
- `signalscope.db`: created at runtime by SQLite and should be ignored by Git.

No real wholesale transaction file was supplied. Consumer spending and fraud datasets mentioned in the case brief are not valid proxies for a wholesale loan, bond, and derivatives book, so the portfolio is explicitly synthetic.
