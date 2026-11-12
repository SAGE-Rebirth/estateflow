def _indian_grouping(n: int) -> str:
    """12345678 → "1,23,45,678" (last three digits, then pairs)."""
    s = str(n)
    head, tail = s[:-3], s[-3:]
    pairs = [head[max(i - 2, 0) : i] for i in range(len(head), 0, -2)][::-1]
    return ",".join([*pairs, tail])


def _scaled(amount: float, unit: float, word: str) -> str:
    return f"{amount / unit:.2f}".rstrip("0").rstrip(".") + f" {word}"


def format_money(amount: float, currency: str) -> str:
    """Price as the assistant should quote it. INR uses Indian grouping plus lakh/crore
    words, so the model copies the figure instead of converting it (and getting it wrong)."""
    if currency.upper() != "INR":
        return f"{currency} {amount:,.0f}"
    text = f"₹{_indian_grouping(round(amount))}"
    if amount >= 1e7:
        return f"{text} ({_scaled(amount, 1e7, 'crore')})"
    if amount >= 1e5:
        return f"{text} ({_scaled(amount, 1e5, 'lakh')})"
    return text
