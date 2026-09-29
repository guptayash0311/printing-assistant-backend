from decimal import Decimal

from app.services.pricing import PriceRule, SegmentQuoteInput, calculate_quote, duplex_sheets


def test_health(client):
    assert client.get("/health/live").json()["status"] == "ok"
    assert client.get("/health/ready").json()["status"] == "ok"


def test_duplex_is_priced_per_physical_sheet():
    assert duplex_sheets(3) == 2
    quote = calculate_quote(
        [
            PriceRule("A4_BW_DUPLEX", "A4", "BW", "DUPLEX", Decimal("3.00"), "SHEET", 1),
        ],
        [
            SegmentQuoteInput("file", 1, 3, "A4", "BW", "DUPLEX", 2, 3, "notes.pdf"),
        ],
        "INR",
    )
    assert quote.line_items[0].quantity == Decimal("4")
    assert quote.grand_total == Decimal("12.00")


def test_simplex_is_priced_per_page():
    quote = calculate_quote(
        [PriceRule("A4_BW_SIMPLEX", "A4", "BW", "SIMPLEX", Decimal("2.00"), "PAGE", 1)],
        [SegmentQuoteInput("file", 1, 3, "A4", "BW", "SIMPLEX", 2, 3, "notes.pdf")],
        "INR",
    )
    assert quote.line_items[0].quantity == Decimal("6")
    assert quote.grand_total == Decimal("12.00")
