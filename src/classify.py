"""Three-way match reconstruction and a MECE exception taxonomy.

THE DIFFERENTIATOR LIVES HERE.

Eighteen percent of supplier invoices fail three-way match. Everyone calls it
"a supplier data problem", the remediation budget goes to a data-quality
programme, and the rate does not move.

The reason is that the categories in the usual analysis overlap. An invoice
that is both short-delivered AND priced wrong lands in two buckets, the
percentages add to more than 100, and the Pareto chart that comes out of it
cannot be acted on because no single fix owns a bar.

So the taxonomy here is MUTUALLY EXCLUSIVE and EXHAUSTIVE, enforced by
construction and verified against a hand-labelled sample:

  - exclusive: causes are evaluated in a fixed precedence order and exactly
    one is assigned, so the percentages mean what they appear to mean;
  - exhaustive: anything unmatched lands in `unclassified`, which is REPORTED.
    A taxonomy that quietly absorbs its failures into "other" is how these
    analyses mislead.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Cause(str, Enum):
    PO_LINE_ROUNDING = "po_line_rounding"
    QUANTITY_SHORT_DELIVERY = "quantity_short_delivery"
    QUANTITY_OVER_DELIVERY = "quantity_over_delivery"
    PRICE_OFF_CONTRACT = "price_off_contract"
    TAX_CODE_MISMATCH = "tax_code_mismatch"
    GOODS_RECEIPT_MISSING = "goods_receipt_missing"
    DUPLICATE_INVOICE = "duplicate_invoice"
    NO_PURCHASE_ORDER = "no_purchase_order"
    UNCLASSIFIED = "unclassified"


#: Handling minutes and penalty exposure per cause. Explicit so the cost
#: weighting can be challenged rather than taken on trust.
HANDLING_MINUTES: dict[Cause, float] = {
    Cause.PO_LINE_ROUNDING: 6.0,
    Cause.QUANTITY_SHORT_DELIVERY: 22.0,
    Cause.QUANTITY_OVER_DELIVERY: 18.0,
    Cause.PRICE_OFF_CONTRACT: 35.0,
    Cause.TAX_CODE_MISMATCH: 12.0,
    Cause.GOODS_RECEIPT_MISSING: 28.0,
    Cause.DUPLICATE_INVOICE: 9.0,
    Cause.NO_PURCHASE_ORDER: 45.0,
    Cause.UNCLASSIFIED: 30.0,
}
#: Probability the exception delays payment past terms, and the average
#: penalty when it does.
LATE_RISK: dict[Cause, float] = {
    Cause.PO_LINE_ROUNDING: 0.05,
    Cause.QUANTITY_SHORT_DELIVERY: 0.35,
    Cause.QUANTITY_OVER_DELIVERY: 0.30,
    Cause.PRICE_OFF_CONTRACT: 0.55,
    Cause.TAX_CODE_MISMATCH: 0.15,
    Cause.GOODS_RECEIPT_MISSING: 0.60,
    Cause.DUPLICATE_INVOICE: 0.05,
    Cause.NO_PURCHASE_ORDER: 0.70,
    Cause.UNCLASSIFIED: 0.40,
}
LABOUR_COST_PER_MINUTE = 0.72
AVERAGE_LATE_PENALTY = 85.0


@dataclass(frozen=True)
class PoLine:
    po_number: str
    line: int
    quantity: float
    unit_price: float
    tax_code: str


@dataclass(frozen=True)
class GoodsReceipt:
    po_number: str
    line: int
    quantity_received: float


@dataclass(frozen=True)
class InvoiceLine:
    invoice_id: str
    supplier: str
    po_number: str | None
    line: int
    quantity: float
    unit_price: float
    tax_code: str


@dataclass(frozen=True)
class MatchContext:
    invoice: InvoiceLine
    po: PoLine | None
    receipt: GoodsReceipt | None
    is_duplicate: bool


#: Tolerances, held as data so a reviewer can change them without touching
#: code - and so the classification is reproducible from a stated policy.
QUANTITY_TOLERANCE = 0.0
#: A unit-price difference at or below this is exactly what rounding a 4dp
#: contract price to 2dp on the invoice produces. It is NOT a pricing dispute.
ROUNDING_UNIT_TOLERANCE = 0.005
#: The match is performed on the LINE TOTAL, which is where the money is.
#: A half-penny per unit is immaterial on a line of 3 and a GBP 1.60 mismatch
#: on a line of 400 - same root cause, and only the second one fails the
#: match. That asymmetry is why the rounding cause hides inside "price
#: dispute" in the usual analysis.
TOTAL_TOLERANCE = 0.50


def classify(ctx: MatchContext) -> Cause:
    """Assign EXACTLY ONE cause, in a fixed precedence order.

    The order is the policy. It is written down here rather than emerging from
    the order of `if` statements by accident, because it determines every
    percentage in the report.
    """
    inv = ctx.invoice

    # 1. A duplicate is a duplicate regardless of what else is wrong with it.
    if ctx.is_duplicate:
        return Cause.DUPLICATE_INVOICE

    # 2. No PO reference at all: nothing downstream can be evaluated.
    if inv.po_number is None or ctx.po is None:
        return Cause.NO_PURCHASE_ORDER

    # 3. No goods receipt: the quantity question is unanswerable.
    if ctx.receipt is None:
        return Cause.GOODS_RECEIPT_MISSING

    po = ctx.po
    receipt = ctx.receipt

    unit_delta = abs(inv.unit_price - po.unit_price)
    quantity_delta = inv.quantity - receipt.quantity_received

    # 4. Quantity first: a short delivery explains a total mismatch on its own.
    if quantity_delta > QUANTITY_TOLERANCE:
        return Cause.QUANTITY_SHORT_DELIVERY
    if quantity_delta < -QUANTITY_TOLERANCE:
        return Cause.QUANTITY_OVER_DELIVERY

    # 5. Rounding is checked BEFORE price. A unit difference within rounding
    #    range is a configuration bug in the price-list export, not a
    #    commercial dispute - and conflating the two is precisely what buries
    #    the single biggest FIXABLE cause inside "price dispute".
    line_total_delta = abs(
        inv.quantity * inv.unit_price - po.quantity * po.unit_price)
    if 0 < unit_delta <= ROUNDING_UNIT_TOLERANCE and line_total_delta > TOTAL_TOLERANCE:
        return Cause.PO_LINE_ROUNDING

    if unit_delta > ROUNDING_UNIT_TOLERANCE:
        return Cause.PRICE_OFF_CONTRACT

    if inv.tax_code != po.tax_code:
        return Cause.TAX_CODE_MISMATCH

    return Cause.UNCLASSIFIED


def matches_cleanly(ctx: MatchContext) -> bool:
    return classify(ctx) is Cause.UNCLASSIFIED and not _has_any_discrepancy(ctx)


def _has_any_discrepancy(ctx: MatchContext) -> bool:
    if ctx.is_duplicate or ctx.po is None or ctx.receipt is None:
        return True
    inv, po, receipt = ctx.invoice, ctx.po, ctx.receipt
    unit_delta = abs(inv.unit_price - po.unit_price)
    total_delta = abs(
        inv.quantity * inv.unit_price - po.quantity * po.unit_price)
    return (
        unit_delta > ROUNDING_UNIT_TOLERANCE
        or total_delta > TOTAL_TOLERANCE
        or abs(inv.quantity - receipt.quantity_received) > QUANTITY_TOLERANCE
        or inv.tax_code != po.tax_code
    )


# ---------------------------------------------------------------------------
# Cost-weighted Pareto
# ---------------------------------------------------------------------------

@ dataclass(frozen=True)
class ParetoRow:
    cause: Cause
    count: int
    share_of_count: float
    annual_cost: float
    share_of_cost: float
    cumulative_cost_share: float
    remediation: str

    @property
    def cost_per_exception(self) -> float:
        return self.annual_cost / self.count if self.count else 0.0


REMEDIATION: dict[Cause, str] = {
    Cause.PO_LINE_ROUNDING:
        "align PO line rounding to 2dp in the ERP price-list export "
        "(configuration, no development)",
    Cause.QUANTITY_SHORT_DELIVERY:
        "enforce receipt confirmation before invoice submission on the "
        "supplier portal",
    Cause.QUANTITY_OVER_DELIVERY:
        "apply a 2% over-delivery tolerance with automatic PO amendment",
    Cause.PRICE_OFF_CONTRACT:
        "block invoice submission at a price outside the contracted rate",
    Cause.TAX_CODE_MISMATCH:
        "derive the tax code from the PO rather than the supplier master",
    Cause.GOODS_RECEIPT_MISSING:
        "chase goods receipt at day 3 instead of at invoice arrival",
    Cause.DUPLICATE_INVOICE:
        "reject on (supplier, invoice number) at the portal",
    Cause.NO_PURCHASE_ORDER:
        "no-PO-no-pay policy, phased by supplier tier",
    Cause.UNCLASSIFIED:
        "REVIEW: these do not fit the taxonomy and must be examined by hand",
}


def cost_of(cause: Cause) -> float:
    labour = HANDLING_MINUTES[cause] * LABOUR_COST_PER_MINUTE
    penalty = LATE_RISK[cause] * AVERAGE_LATE_PENALTY
    return labour + penalty


def pareto(contexts: list[MatchContext], annualise: float = 1.0) -> list[ParetoRow]:
    exceptions = [
        (ctx, classify(ctx)) for ctx in contexts if _has_any_discrepancy(ctx)
    ]
    counts: dict[Cause, int] = {}
    for _, cause in exceptions:
        counts[cause] = counts.get(cause, 0) + 1

    total_count = sum(counts.values()) or 1
    costs = {c: n * cost_of(c) * annualise for c, n in counts.items()}
    total_cost = sum(costs.values()) or 1.0

    rows: list[ParetoRow] = []
    cumulative = 0.0
    for cause, cost in sorted(costs.items(), key=lambda kv: -kv[1]):
        cumulative += cost / total_cost
        rows.append(ParetoRow(
            cause=cause,
            count=counts[cause],
            share_of_count=counts[cause] / total_count,
            annual_cost=cost,
            share_of_cost=cost / total_cost,
            cumulative_cost_share=cumulative,
            remediation=REMEDIATION[cause],
        ))
    return rows
