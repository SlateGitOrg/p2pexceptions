# p2pexceptions

> Invoice exception analysis with a MECE cause taxonomy validated against hand labels, so the percentages actually mean something.

`COMPACT` · **Business Analyst** · Intermediate · ~5 days · Manufacturing - procure-to-pay

**Primary language:** SQL
**Tags:** `procure-to-pay`, `dbt`, `sql`, `classification`, `pareto`, `root-cause`

---

> **Implementation note.** The catalogue specifies **SQL** for this
> project and that remains the target. This repository ships a runnable
> **Python** reference implementation of the core differentiator so the
> behaviour is executable and tested today; port it to SQL as step one
> of your own build.

## The problem

Eighteen percent of supplier invoices fail three-way match and land in an exception queue that two people clear manually - roughly 400k a year in labour and late-payment penalties. Everyone calls it a supplier data problem, nobody has decomposed it, and so the remediation budget goes to a data-quality initiative that does not touch the actual causes.

## ⭐ The differentiator

Classifies every exception into a **mutually exclusive, exhaustive (MECE) cause taxonomy validated against a hand-labelled sample**, then computes a cost-weighted Pareto. The recommendation becomes 'three PO-line rounding rules cause 41% of exceptions and are fixable in configuration', not 'improve data quality'. The MECE validation is what generic analyses skip - which is why their categories overlap and their percentages do not sum to anything meaningful.

This is the sentence to lead with when someone asks you to walk through the
project. Everything else in this repo exists to make it true and to prove it.

## Data

A documented synthetic procure-to-pay generator (purchase orders, goods receipts, invoices) with **seeded exception causes at known rates**, plus a hand-labelled validation sample for measuring classifier agreement.

> No paid API key is required to run or demo this project. Where a paid
> service would add value it is wired as an optional enhancement behind an
> interface with an offline mock as the default implementation.

## Stack

- PostgreSQL, dbt with tests
- Python for the classifier
- Streamlit or an Excel export - the audience uses Excel, and that is fine
- dbt tests + pytest

## Core capabilities

- Three-way-match reconstruction with tolerance rules held as configurable data
- MECE cause classifier with an unclassified bucket that must stay below a stated threshold
- Cost weighting per exception (handling minutes plus penalty exposure)
- Supplier and PO-type segmentation with volume-adjusted rates
- Fix-recommendation table with an estimated annual saving per fix

## Repository layout

```
models/
src/classify/
validation/
generator/
tests/
output/
```

## Build plan

1. Define the taxonomy on paper and test it for MECE-ness by hand on fifty real-looking exceptions before writing code.
2. Reconstruct the three-way match with tolerances as data.
3. Classifier, then agreement against hand labels.
4. Cost weighting and the recommendation table last - that table is the deliverable.

## Testing strategy

Assert classifier agreement with the hand-labelled sample is at least 95%. Assert categories are **mutually exclusive** - no invoice receives two causes - and **exhaustive**, with unclassified below 3%. Without those two assertions the Pareto chart is decoration.

Tests assert **correctness**, not merely that the code runs. A green suite on
this repo is a claim about behaviour under adversarial conditions; treat any
test that would pass against a deliberately broken implementation as a bug in
the test.

## Quality & safety layer

The unclassified bucket is always reported, never hidden. A taxonomy that quietly absorbs its failures into an 'other' category is how these analyses mislead.

## Measurable outcome

> A cost-weighted Pareto where the top three bars each carry a named, costed remediation - redirecting a data-quality programme to three configuration changes.

State it in these terms — business units, not technical ones — in your CV
bullet and in the first thirty seconds of describing the project.

## Interview questions this project answers

- **What does MECE mean and why does it matter here?**
- **How did you validate the classification?**
- **Why cost-weight the Pareto rather than count-weight it?**

## What this deliberately is *not*

- Not an OCR or invoice-capture project. It starts from structured records.


## Run it now

```bash
python -m unittest discover -s tests -v   # the suite
python -m src.demo                        # the 60-second artefact
```

Requires Python 3.11+. The runnable core uses **only the standard
library** (including `sqlite3`), so there is nothing to install.

## Getting started

```bash
git clone <your-fork-url> p2pexceptions
cd p2pexceptions
docker compose up -d
python -m generator --invoices 400000
dbt build
python -m src.classify run
pytest validation/               # MECE + 95% agreement
```

Docker is supported but optional — every path above works on a plain
Windows/macOS/Linux laptop without a cloud account.

## Definition of done

- [ ] The differentiator above is implemented, and a test proves it
- [ ] The measurable outcome is produced by a command anyone can run
- [ ] `README` explains the one decision a generic version gets wrong
- [ ] CI runs the full suite on every push and is green on `main`
- [ ] A recruiter can see the headline artefact in under 60 seconds

## Licence

MIT — see [LICENSE](LICENSE).
