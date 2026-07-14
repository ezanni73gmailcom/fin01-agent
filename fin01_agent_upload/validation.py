"""
Validazione dati pratica — evita che campi lasciati vuoti o con segnaposto
("nessuna", "nessuno", "n/d"...) passino silenziosamente all'analisi.
"""

PLACEHOLDER = {"", "nessuna", "nessuno", "n/d", "nd", "na", "non specificato", "da definire", "-"}

CAMPI_OBBLIGATORI = [
    "strumento",
    "isin_o_ticker",
    "mercato",
    "valuta",
    "tesi_speculativa",
    "orizzonte",
    "esperienza_investitore",
    "frequenza_monitoraggio",
]


def _is_placeholder(value) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in PLACEHOLDER


def validate_dati(dati: dict) -> list:
    """Ritorna la lista dei nomi campo mancanti o segnaposto. Lista vuota = tutto ok."""
    return [c for c in CAMPI_OBBLIGATORI if _is_placeholder(dati.get(c))]
