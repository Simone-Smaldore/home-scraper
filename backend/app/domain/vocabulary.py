"""Closed vocabularies.

Values are product text (Italian, shown on screen and stored as-is), names are
identifiers. Adding a value is cheap; renaming one means a migration.
"""

from enum import StrEnum


class SourceName(StrEnum):
    SUBITO = "subito"
    IMMOBILIARE = "immobiliare"


class Zone(StrEnum):
    """Turin, split the way Subito splits it: fourteen areas that partition the city.

    This is the shared vocabulary every source maps onto. Subito defines it
    natively (zone keys 001272-1 … 001272-14); Immobiliare uses finer
    neighbourhoods that fold into these. The user's target areas are a subset,
    see criteria.TARGET_ZONES.
    """

    CENTRO = "Centro"
    CROCETTA = "Crocetta / San Secondo"
    SAN_SALVARIO = "San Salvario"
    NIZZA_MILLEFONTI = "Nizza Millefonti / Precollina"
    SANTA_RITA = "Lingotto / Santa Rita"
    CENISIA = "Cenisia / San Paolo"
    CIT_TURIN = "Cit Turin / San Donato / Campidoglio"
    AURORA = "Valdocco / Aurora"
    VANCHIGLIA = "Vanchiglia / Regio Parco"
    BARRIERA_MILANO = "Barriera di Milano / Falchera"
    MADONNA_DI_CAMPAGNA = "Madonna di Campagna / Borgo Vittoria"
    LUCENTO = "Lucento / Vallette"
    PARELLA = "Parella / Pozzo Strada"
    MIRAFIORI = "Mirafiori"


class Garage(StrEnum):
    BOX = "box"
    POSTO_AUTO = "posto auto"
    NONE = "nessuno"


class Condition(StrEnum):
    DA_RISTRUTTURARE = "da ristrutturare"
    ABITABILE = "abitabile"
    RISTRUTTURATO = "ristrutturato"


class ReviewStatus(StrEnum):
    """What you said about a listing. "Nuova" is the absence of a review row."""

    NUOVA = "nuova"
    INTERESSANTE = "interessante"
    MEDIA = "media"
    SCARTATA = "scartata"
