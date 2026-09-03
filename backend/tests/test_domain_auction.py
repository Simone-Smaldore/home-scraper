import pytest

from app.domain.auction import is_auction


@pytest.mark.parametrize(
    "text",
    [
        "Immobile in asta di 96 m² con 3 locali a Torino",
        "Appartamento all'asta, Tribunale di Torino",
        "ASTA GIUDIZIARIA - trilocale",
        "vendita giudiziaria senza incanto",
    ],
)
def test_auction_wording_is_recognized(text: str) -> None:
    assert is_auction(text)


@pytest.mark.parametrize(
    "text",
    ["Fantastica vista sulla collina", "A due passi da piazza Castello", "", None],
)
def test_ordinary_text_is_not_an_auction(text: str | None) -> None:
    assert not is_auction(text)


def test_any_of_the_texts_counts() -> None:
    assert is_auction("Trilocale luminoso", "Vendita all'asta il 12/10")
