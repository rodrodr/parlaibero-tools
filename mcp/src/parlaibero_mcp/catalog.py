"""The sixteen ParlaIbero datasets deposited in Harvard Dataverse, one DOI per country."""
from __future__ import annotations

COLLECTION_URL = "https://dataverse.harvard.edu/dataverse/parlaibero"

# ISO2 → (English name, Spanish/Portuguese name, DOI)
PARLAIBERO: dict[str, tuple[str, str, str]] = {
    "AR": ("Argentina", "Argentina", "10.7910/DVN/IVNYID"),
    "BR": ("Brazil", "Brasil", "10.7910/DVN/VTXNW3"),
    "CL": ("Chile", "Chile", "10.7910/DVN/IKBNRL"),
    "CO": ("Colombia", "Colombia", "10.7910/DVN/TYYERX"),
    "CR": ("Costa Rica", "Costa Rica", "10.7910/DVN/W6UAHQ"),
    "DO": ("Dominican Republic", "República Dominicana", "10.7910/DVN/DZKXUG"),
    "EC": ("Ecuador", "Ecuador", "10.7910/DVN/M2QJN6"),
    "ES": ("Spain", "España", "10.7910/DVN/OKHGAB"),
    "GT": ("Guatemala", "Guatemala", "10.7910/DVN/NH5TTC"),
    "MX": ("Mexico", "México", "10.7910/DVN/0IS1YE"),
    "PA": ("Panama", "Panamá", "10.7910/DVN/Y8FUSX"),
    "PE": ("Peru", "Perú", "10.7910/DVN/7MK94V"),
    "PT": ("Portugal", "Portugal", "10.7910/DVN/VRPUFU"),
    "PY": ("Paraguay", "Paraguay", "10.7910/DVN/PDX8GA"),
    "SV": ("El Salvador", "El Salvador", "10.7910/DVN/MUJU6A"),
    "UY": ("Uruguay", "Uruguay", "10.7910/DVN/KI1AOC"),
}

# The datasets of the collection being served (the active profile, see profile.py). Modules import
# this dict by name: profile.activate refills it in place.
COUNTRIES: dict[str, tuple[str, str, str]] = dict(PARLAIBERO)

# Documentation files deposited with every dataset: key → (file stem, has es/pt translations)
DOCUMENTS: dict[str, tuple[str, bool]] = {
    "readme": ("README", True),
    "data_dictionary": ("data_dictionary", True),
    "known_limitations": ("known_limitations", True),
    "process_report": ("process_report", True),
    "corpus_info": ("corpus_info", False),
    "match_methods": ("match_methods", False),
    "dataset_jsonld": ("dataset", False),
}


def normalize_iso(country: str) -> str:
    """Accept 'es', 'ES', 'Spain', 'España'… and return the ISO2 code, or raise ValueError."""
    c = (country or "").strip()
    if c.upper() in COUNTRIES:
        return c.upper()
    low = c.lower()
    for iso, (en, local, _) in COUNTRIES.items():
        if low in (en.lower(), local.lower()):
            return iso
    raise ValueError(f"Unknown country {country!r}. Use one of: {', '.join(COUNTRIES)}")


def document_filename(doc: str, language: str = "en") -> str:
    if doc not in DOCUMENTS:
        raise ValueError(f"Unknown document {doc!r}. Use one of: {', '.join(DOCUMENTS)}")
    stem, translated = DOCUMENTS[doc]
    if doc == "corpus_info" or doc == "match_methods":
        return f"{stem}.json"
    if doc == "dataset_jsonld":
        return "dataset.jsonld"
    lang = (language or "en").lower()[:2]
    if translated and lang in ("es", "pt"):
        return f"{stem}_{lang}.md"
    return f"{stem}.md"
