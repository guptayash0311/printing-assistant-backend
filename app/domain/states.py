TRANSITIONS: set[tuple[str, str]] = {
    ("DRAFT", "UPLOADED"),
    ("UPLOADED", "PRICE_CALCULATED"),
    ("PRICE_CALCULATED", "PENDING_APPROVAL"),
    ("PENDING_APPROVAL", "APPROVED"),
    ("PENDING_APPROVAL", "REJECTED"),
    ("APPROVED", "PAID"),
    ("PAID", "PRINTING"),
    ("PRINTING", "READY"),
    ("PRINTING", "PRINT_FAILED"),
    ("READY", "COMPLETED"),
}


def assert_transition(current: str, target: str) -> None:
    from app.core.errors import DomainError

    if (current, target) not in TRANSITIONS:
        raise DomainError(
            "INVALID_ORDER_STATE",
            f"Cannot move from {current} to {target}.",
            409,
        )
