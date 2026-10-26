"""Generate synthetic invoice data and print a cost-weighted Pareto with a remediation per cause.

Run: python -m src.demo
"""

from __future__ import annotations

from .classify import Cause, classify, pareto
from .generator import generate, validation_sample

INVOICES = 400_000
#: The log covers one quarter.
ANNUALISE = 4.0


def main() -> None:
    cases, rates = generate(invoices=INVOICES, seed=20260911)
    contexts = [c.context for c in cases]
    rows = pareto(contexts, annualise=ANNUALISE)

    exceptions = sum(r.count for r in rows)
    print("\n  p2pexceptions - invoice exception report (synthetic data)")
    print("  " + "=" * 78)
    print(f"  {INVOICES:,} invoice lines, {exceptions:,} failed three-way match "
          f"({exceptions / INVOICES:.1%}).\n")

    sample = validation_sample(cases, size=800)
    agreed = sum(1 for c in sample if classify(c.context) is c.true_cause)
    print(f"  Classifier agreement with a generator-labelled sample of "
          f"{len(sample)}: {agreed / len(sample):.1%}")
    unclassified = next(
        (r for r in rows if r.cause is Cause.UNCLASSIFIED), None)
    share = unclassified.share_of_count if unclassified else 0.0
    print(f"  Unclassified: {share:.2%} (reported, not folded into 'other')\n")

    print("  COST-WEIGHTED PARETO")
    print("  " + "-" * 78)
    print(f"  {'cause':<26}{'count':>8}{'% count':>9}{'annual cost':>14}"
          f"{'% cost':>8}{'cum':>7}")
    print("  " + "-" * 78)
    for r in rows:
        print(f"  {r.cause.value:<26}{r.count:>8,}{r.share_of_count:>9.1%}"
              f"{r.annual_cost:>14,.0f}{r.share_of_cost:>8.1%}"
              f"{r.cumulative_cost_share:>7.0%}")

    total = sum(r.annual_cost for r in rows)
    print(f"\n  Total annual cost of the exception queue: GBP {total:,.0f}\n")

    by_count = sorted(rows, key=lambda r: -r.count)
    print("  RANKED BY COUNT vs RANKED BY COST")
    print("  " + "-" * 78)
    print(f"    {'#':<4}{'by count':<28}{'by cost':<28}")
    for i in range(min(4, len(rows))):
        print(f"    {i + 1:<4}{by_count[i].cause.value:<28}{rows[i].cause.value:<28}")
    print("\n    The orderings differ: the most frequent cause is not the most")
    print("    expensive one.\n")

    print("  TOP THREE CAUSES BY COST, WITH REMEDIATION")
    print("  " + "-" * 78)
    for r in rows[:3]:
        print(f"    {r.cause.value}  -  GBP {r.annual_cost:,.0f}/yr "
              f"({r.share_of_cost:.0%} of the queue cost)")
        print(f"      {r.remediation}")
    print(f"\n    These three are {rows[2].cumulative_cost_share:.0%} of the cost.")

    rounding = next(r for r in rows if r.cause is Cause.PO_LINE_ROUNDING)
    rank_by_cost = rows.index(rounding) + 1
    rank_by_count = by_count.index(rounding) + 1
    print("\n  PO LINE ROUNDING")
    print("  " + "-" * 78)
    print(f"    po_line_rounding is #{rank_by_count} by COUNT "
          f"({rounding.share_of_count:.0%} of the queue) and only "
          f"#{rank_by_cost} by cost.")
    print(f"    It is GBP {rounding.annual_cost:,.0f}/yr and "
          f"{rounding.cost_per_exception:.0f} per exception.")
    print("    Cause:")
    print("    the contract price carries 4dp, the invoice rounds to 2dp, and")
    print("    on a 300-unit line that becomes a GBP 1.20 mismatch. The same")
    print("    rounding on a 3-unit line matches cleanly, so it is easily")
    print("    mistaken for a price dispute.")
    print(f"\n    Removing it clears {rounding.share_of_count:.0%} of the "
          "queue volume for a configuration")
    print("    change, which is a separate decision from the cost ranking.\n")


if __name__ == "__main__":
    main()
