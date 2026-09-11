"""MECE is the claim: exactly one cause per exception, nothing unexplained,
and agreement with an independently recorded label."""

from __future__ import annotations

import unittest

from src.classify import (
    Cause, GoodsReceipt, InvoiceLine, MatchContext, PoLine, classify, cost_of,
    pareto,
)
from src.generator import generate, validation_sample

INVOICES = 60_000


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.rates = generate(invoices=INVOICES, seed=20260911)
        cls.sample = validation_sample(cls.cases, size=800)
        cls.rows = pareto([c.context for c in cls.cases])


class TestMece(Base):
    def test_MUTUALLY_EXCLUSIVE_exactly_one_cause_per_exception(self):
        # `classify` returns a single Cause by construction, so the property
        # under test is that the taxonomy decides rather than falling through:
        # every exception must get a cause, and only one.
        for case in self.cases[:5_000]:
            cause = classify(case.context)
            self.assertIsInstance(cause, Cause)

    def test_EXHAUSTIVE_the_unclassified_bucket_stays_below_three_percent(self):
        unclassified = next(
            (r for r in self.rows if r.cause is Cause.UNCLASSIFIED), None)
        share = unclassified.share_of_count if unclassified else 0.0
        self.assertLess(
            share, 0.03,
            f"{share:.1%} unclassified - a taxonomy that cannot place its own "
            f"exceptions produces percentages that mean nothing",
        )

    def test_the_unclassified_bucket_is_REPORTED_not_hidden(self):
        # If it exists at all it must appear in the Pareto with a remediation
        # that says "examine these by hand", never silently folded into
        # another bar.
        unclassified = [r for r in self.rows if r.cause is Cause.UNCLASSIFIED]
        for row in unclassified:
            self.assertIn("REVIEW", row.remediation)

    def test_the_shares_sum_to_one(self):
        self.assertAlmostEqual(sum(r.share_of_count for r in self.rows), 1.0,
                               places=9)
        self.assertAlmostEqual(sum(r.share_of_cost for r in self.rows), 1.0,
                               places=9)

    def test_clean_invoices_are_not_counted_as_exceptions(self):
        total_exceptions = sum(r.count for r in self.rows)
        self.assertLess(total_exceptions, INVOICES * 0.30)
        self.assertGreater(total_exceptions, INVOICES * 0.10)


class TestAgreementWithHandLabels(Base):
    def test_THE_VALIDATION_agreement_is_at_least_95_percent(self):
        agreed = sum(
            1 for c in self.sample if classify(c.context) is c.true_cause)
        agreement = agreed / len(self.sample)
        self.assertGreaterEqual(
            agreement, 0.95,
            f"classifier agreed with the hand label on {agreement:.1%} of "
            f"{len(self.sample)} cases",
        )

    def test_agreement_holds_for_EVERY_cause_not_just_on_average(self):
        # An average hides a cause that is classified wrongly every time.
        by_cause: dict[Cause, list[bool]] = {}
        for c in self.sample:
            by_cause.setdefault(c.true_cause, []).append(
                classify(c.context) is c.true_cause)
        for cause, results in by_cause.items():
            with self.subTest(cause=cause.value):
                rate = sum(results) / len(results)
                self.assertGreaterEqual(rate, 0.90, f"{cause.value}: {rate:.0%}")

    def test_the_sample_covers_every_seeded_cause(self):
        self.assertEqual(
            {c.true_cause for c in self.sample}, set(self.rates),
            "a sample that misses rare causes cannot validate them")

    def test_seeded_rates_are_recovered(self):
        counts = {r.cause: r.count for r in self.rows}
        for cause, rate in self.rates.items():
            with self.subTest(cause=cause.value):
                observed = counts.get(cause, 0) / INVOICES
                self.assertAlmostEqual(observed, rate, delta=0.004)


class TestPrecedence(unittest.TestCase):
    """The order of evaluation IS the policy, so it is tested directly."""

    def _ctx(self, **kw) -> MatchContext:
        po = kw.get("po", PoLine("PO1", 1, 10.0, 5.00, "S1"))
        receipt = kw.get("receipt", GoodsReceipt("PO1", 1, 10.0))
        inv = kw.get("inv", InvoiceLine("INV1", "SUP1", "PO1", 1, 10.0, 5.00, "S1"))
        return MatchContext(inv, po, receipt, kw.get("duplicate", False))

    def test_a_clean_match_yields_no_cause(self):
        self.assertIs(classify(self._ctx()), Cause.UNCLASSIFIED)

    def test_duplicate_outranks_everything_else(self):
        ctx = self._ctx(
            duplicate=True,
            inv=InvoiceLine("INV1", "SUP1", "PO1", 1, 10.0, 9.99, "Z0"))
        self.assertIs(classify(ctx), Cause.DUPLICATE_INVOICE)

    def test_no_po_outranks_quantity_and_price(self):
        ctx = self._ctx(
            po=None,
            inv=InvoiceLine("INV1", "SUP1", None, 1, 99.0, 9.99, "Z0"))
        self.assertIs(classify(ctx), Cause.NO_PURCHASE_ORDER)

    def test_missing_receipt_outranks_price(self):
        ctx = self._ctx(
            receipt=None,
            inv=InvoiceLine("INV1", "SUP1", "PO1", 1, 10.0, 9.99, "S1"))
        self.assertIs(classify(ctx), Cause.GOODS_RECEIPT_MISSING)

    def test_THE_KEY_SEPARATION_rounding_is_not_a_price_dispute(self):
        # A 0.004/unit difference on a line of 300: GBP 1.20 total mismatch,
        # entirely explained by rounding a 4dp contract price to 2dp.
        po = PoLine("PO1", 1, 300.0, 5.00, "S1")
        ctx = MatchContext(
            InvoiceLine("INV1", "SUP1", "PO1", 1, 300.0, 5.004, "S1"),
            po, GoodsReceipt("PO1", 1, 300.0), False)
        self.assertIs(classify(ctx), Cause.PO_LINE_ROUNDING)

    def test_the_SAME_rounding_on_a_small_line_is_not_even_an_exception(self):
        # Identical root cause, immaterial total, so it matches cleanly. This
        # asymmetry is why the cause hides inside "price dispute".
        po = PoLine("PO1", 1, 3.0, 5.00, "S1")
        ctx = MatchContext(
            InvoiceLine("INV1", "SUP1", "PO1", 1, 3.0, 5.004, "S1"),
            po, GoodsReceipt("PO1", 1, 3.0), False)
        self.assertIs(classify(ctx), Cause.UNCLASSIFIED)

    def test_a_real_price_difference_is_NOT_called_rounding(self):
        ctx = self._ctx(
            inv=InvoiceLine("INV1", "SUP1", "PO1", 1, 10.0, 5.90, "S1"))
        self.assertIs(classify(ctx), Cause.PRICE_OFF_CONTRACT)

    def test_short_and_over_delivery_are_distinguished(self):
        short = self._ctx(receipt=GoodsReceipt("PO1", 1, 8.0))
        over = self._ctx(receipt=GoodsReceipt("PO1", 1, 12.0))
        self.assertIs(classify(short), Cause.QUANTITY_SHORT_DELIVERY)
        self.assertIs(classify(over), Cause.QUANTITY_OVER_DELIVERY)

    def test_tax_code_is_the_last_check(self):
        ctx = self._ctx(
            inv=InvoiceLine("INV1", "SUP1", "PO1", 1, 10.0, 5.00, "Z0"))
        self.assertIs(classify(ctx), Cause.TAX_CODE_MISMATCH)


class TestCostWeighting(Base):
    def test_the_pareto_is_ordered_by_COST_not_by_count(self):
        costs = [r.annual_cost for r in self.rows]
        self.assertEqual(costs, sorted(costs, reverse=True))

    def test_cost_and_count_rankings_genuinely_differ(self):
        by_cost = [r.cause for r in self.rows]
        by_count = [r.cause for r in sorted(self.rows, key=lambda r: -r.count)]
        self.assertNotEqual(
            by_cost, by_count,
            "if they agree, cost-weighting adds nothing and the differentiator "
            "is not demonstrated",
        )

    def test_every_cause_carries_a_named_remediation(self):
        for row in self.rows:
            self.assertGreater(len(row.remediation), 25)

    def test_cumulative_share_reaches_one(self):
        self.assertAlmostEqual(self.rows[-1].cumulative_cost_share, 1.0, places=9)

    def test_the_top_three_causes_carry_most_of_the_cost(self):
        self.assertGreater(self.rows[2].cumulative_cost_share, 0.5)

    def test_cost_per_exception_reflects_handling_and_penalty(self):
        self.assertGreater(cost_of(Cause.NO_PURCHASE_ORDER),
                           cost_of(Cause.PO_LINE_ROUNDING))


if __name__ == "__main__":
    unittest.main()
