from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.core.errors import DomainError

TWOPLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PriceRule:
    code: str
    paper_size: str
    color_mode: str
    sides: str
    unit_price: Decimal
    unit: str
    version: int


@dataclass(frozen=True)
class SegmentQuoteInput:
    file_id: str
    page_start: int
    page_end: int
    paper_size: str
    color_mode: str
    sides: str
    copies: int
    page_count: int
    filename: str


@dataclass(frozen=True)
class LineQuote:
    description: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal
    metadata: dict


@dataclass(frozen=True)
class Quote:
    currency: str
    pricing_version: int
    line_items: list[LineQuote]
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    service_fee: Decimal
    grand_total: Decimal


def duplex_sheets(pages: int) -> int:
    return (pages + 1) // 2


def calculate_quote(rules: list[PriceRule], segments: list[SegmentQuoteInput], currency: str) -> Quote:
    if not segments:
        raise DomainError(
            "INVALID_PRINT_CONFIGURATION",
            "Add at least one print range.",
            400,
        )
    lines: list[LineQuote] = []
    versions: list[int] = []
    for segment in segments:
        pages = segment.page_end - segment.page_start + 1
        if pages < 1 or segment.page_start < 1 or segment.page_end > segment.page_count:
            raise DomainError(
                "INVALID_PRINT_CONFIGURATION",
                "Page range is outside the document.",
                400,
            )
        if segment.copies < 1:
            raise DomainError("INVALID_PRINT_CONFIGURATION", "Copies must be at least 1.", 400)
        rule = _match_rule(rules, segment)
        versions.append(rule.version)
        if segment.sides == "DUPLEX":
            quantity = duplex_sheets(pages) * segment.copies
            unit_label = "sheet"
        else:
            quantity = pages * segment.copies
            unit_label = "page"
        quantity_decimal = Decimal(quantity)
        total = money(rule.unit_price * quantity_decimal)
        description = (
            f"{segment.filename} p.{segment.page_start}-{segment.page_end} "
            f"{segment.paper_size} {segment.color_mode} {segment.sides} x{segment.copies}"
        )
        lines.append(
            LineQuote(
                description=description,
                quantity=quantity_decimal,
                unit_price=money(rule.unit_price),
                total=total,
                metadata={
                    "file_id": segment.file_id,
                    "code": rule.code,
                    "unit": rule.unit,
                    "unit_label": unit_label,
                    "paper_size": segment.paper_size,
                    "color_mode": segment.color_mode,
                    "sides": segment.sides,
                    "copies": segment.copies,
                },
            )
        )
    subtotal = money(sum((line.total for line in lines), Decimal("0")))
    zero = money(Decimal("0"))
    return Quote(
        currency=currency,
        pricing_version=max(versions),
        line_items=lines,
        subtotal=subtotal,
        discount_total=zero,
        tax_total=zero,
        service_fee=zero,
        grand_total=subtotal,
    )


def _match_rule(rules: list[PriceRule], segment: SegmentQuoteInput) -> PriceRule:
    for rule in rules:
        if (
            rule.paper_size == segment.paper_size
            and rule.color_mode == segment.color_mode
            and rule.sides == segment.sides
        ):
            expected = "SHEET" if segment.sides == "DUPLEX" else "PAGE"
            if rule.unit != expected:
                continue
            return rule
    raise DomainError(
        "PRICE_CALCULATION_FAILED",
        "No price is set for this paper, color, and sides combination.",
        400,
    )
