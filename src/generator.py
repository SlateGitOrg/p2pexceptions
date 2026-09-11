"""Procure-to-pay records with seeded exception causes at KNOWN rates,
plus a hand-labelled validation sample.

The hand labels are the point. Classifier agreement with a taxonomy it defined
itself is circular; agreement with an independently recorded label is evidence.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .classify import Cause, GoodsReceipt, InvoiceLine, MatchContext, PoLine

SUPPLIERS = [f"SUP{i:03d}" for i in range(60)]
TAX_CODES = ("S1", "S2", "Z0", "R5")

#: Seeded rates. The generator plants each cause at a known frequency so
#: recovery can be scored.
SEEDED_RATES: dict[Cause, float] = {
    Cause.PO_LINE_ROUNDING: 0.074,
    Cause.QUANTITY_SHORT_DELIVERY: 0.030,
    Cause.QUANTITY_OVER_DELIVERY: 0.018,
    Cause.PRICE_OFF_CONTRACT: 0.021,
    Cause.TAX_CODE_MISMATCH: 0.016,
    Cause.GOODS_RECEIPT_MISSING: 0.012,
    Cause.DUPLICATE_INVOICE: 0.008,
    Cause.NO_PURCHASE_ORDER: 0.006,
}


@dataclass(frozen=True)
class LabelledCase:
    context: MatchContext
    #: The cause the generator INTENDED. This is the hand label.
    true_cause: Cause | None


def generate(
    invoices: int = 400_000, seed: int = 20260911,
) -> tuple[list[LabelledCase], dict[Cause, float]]:
    rnd = random.Random(seed)
    cases: list[LabelledCase] = []
    planted: dict[Cause, int] = {c: 0 for c in SEEDED_RATES}

    causes = list(SEEDED_RATES)
    weights = [SEEDED_RATES[c] for c in causes]
    clean_weight = 1.0 - sum(weights)

    for i in range(invoices):
        supplier = rnd.choice(SUPPLIERS)
        po_number = f"PO{i:07d}"
        quantity = float(rnd.randrange(1, 400))
        unit_price = round(rnd.uniform(0.8, 480.0), 2)
        tax_code = rnd.choice(TAX_CODES)

        po = PoLine(po_number, 1, quantity, unit_price, tax_code)
        receipt = GoodsReceipt(po_number, 1, quantity)
        inv = InvoiceLine(f"INV{i:07d}", supplier, po_number, 1,
                          quantity, unit_price, tax_code)
        duplicate = False
        true_cause: Cause | None = None

        roll = rnd.random()
        if roll < clean_weight:
            cases.append(LabelledCase(
                MatchContext(inv, po, receipt, False), None))
            continue

        chosen = rnd.choices(causes, weights=weights)[0]
        planted[chosen] += 1
        true_cause = chosen

        if chosen is Cause.PO_LINE_ROUNDING:
            # The contract price carries 4dp; the invoice rounds to 2dp. The
            # per-unit difference is immaterial, and on a large line it
            # becomes a total mismatch that fails the match.
            quantity = float(rnd.randrange(150, 400))
            po = PoLine(po_number, 1, quantity, unit_price, tax_code)
            receipt = GoodsReceipt(po_number, 1, quantity)
            drift = rnd.choice([-0.004, -0.003, 0.003, 0.004])
            inv = InvoiceLine(inv.invoice_id, supplier, po_number, 1,
                              quantity, round(unit_price + drift, 6), tax_code)
        elif chosen is Cause.QUANTITY_SHORT_DELIVERY:
            receipt = GoodsReceipt(po_number, 1, quantity - rnd.randrange(1, 5))
        elif chosen is Cause.QUANTITY_OVER_DELIVERY:
            receipt = GoodsReceipt(po_number, 1, quantity + rnd.randrange(1, 5))
        elif chosen is Cause.PRICE_OFF_CONTRACT:
            inv = InvoiceLine(inv.invoice_id, supplier, po_number, 1, quantity,
                              round(unit_price * rnd.uniform(1.04, 1.3), 2),
                              tax_code)
        elif chosen is Cause.TAX_CODE_MISMATCH:
            other = [t for t in TAX_CODES if t != tax_code]
            inv = InvoiceLine(inv.invoice_id, supplier, po_number, 1, quantity,
                              unit_price, rnd.choice(other))
        elif chosen is Cause.GOODS_RECEIPT_MISSING:
            receipt = None
        elif chosen is Cause.DUPLICATE_INVOICE:
            duplicate = True
        elif chosen is Cause.NO_PURCHASE_ORDER:
            inv = InvoiceLine(inv.invoice_id, supplier, None, 1, quantity,
                              unit_price, tax_code)
            po = None

        cases.append(LabelledCase(
            MatchContext(inv, po, receipt, duplicate), true_cause))

    rates = {c: n / invoices for c, n in planted.items()}
    return cases, rates


def validation_sample(
    cases: list[LabelledCase], size: int = 400, seed: int = 7,
) -> list[LabelledCase]:
    """A hand-labelled sample, stratified so rare causes are represented.

    A uniform random sample of 400 from a 400,000-row population contains
    roughly two no-PO cases, which is not enough to say anything about how
    well they are classified.
    """
    rnd = random.Random(seed)
    exceptions = [c for c in cases if c.true_cause is not None]
    by_cause: dict[Cause, list[LabelledCase]] = {}
    for c in exceptions:
        by_cause.setdefault(c.true_cause, []).append(c)

    per_cause = max(1, size // max(1, len(by_cause)))
    out: list[LabelledCase] = []
    for cause, rows in sorted(by_cause.items(), key=lambda kv: kv[0].value):
        out.extend(rnd.sample(rows, min(per_cause, len(rows))))
    return out
