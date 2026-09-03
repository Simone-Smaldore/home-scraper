"""Italian number formatting for the few units the product shows.

Thousands with a dot, a space before the unit: "250.000 €", "85 mq". Used by
the CLI output today and mirrored by frontend/src/lib/format.ts later.
"""


def eur(value: int) -> str:
    return f"{value:,}".replace(",", ".") + " €"


def sqm(value: int) -> str:
    return f"{value} mq"
