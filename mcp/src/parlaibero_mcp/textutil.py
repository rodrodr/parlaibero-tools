"""Text matching shared by every tool: accent-tolerant RE2 patterns, tokens and stopwords.

One definition of a token everywhere: a maximal run of letters, digits or combining marks, lower-cased,
accents folded for counting. `n_words`, the precomputed unigram table and every count use it, so
per-million figures from different tools are comparable.
"""
from __future__ import annotations

import re
import unicodedata

_FOLD = {"a": "aáàâãä", "e": "eéèêë", "i": "iíìîï", "o": "oóòôõö", "u": "uúùûü",
         "c": "cç", "n": "nñ", "y": "yý"}
_FOLD_REV = {ch: base for base, chars in _FOLD.items() for ch in chars}

TOKEN_SQL = r"[\pL\pN\pM]+"
NONTOKEN_SQL = r"[^\pL\pN]+"
_TOKEN_PY = re.compile(r"[^\W_]+", re.UNICODE)


def fold(s: str) -> str:
    """Lower-case and strip diacritics (same result as DuckDB strip_accents(lower(s)))."""
    nf = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in nf if unicodedata.category(c) != "Mn")


def tokens(text: str) -> list[str]:
    """Tokens of a text. NFC first, so a decomposed accent does not split a word."""
    return _TOKEN_PY.findall(unicodedata.normalize("NFC", text).lower()) if text else []


def _literal(word: str) -> str:
    out = []
    for ch in word.lower():
        base = _FOLD_REV.get(ch)
        if base:
            out.append(f"[{_FOLD[base]}]" + r"\pM*")   # \pM*: tolerate decomposed accents
        elif ch.isalnum():
            out.append(ch + r"\pM*")
        elif ch.isspace():
            out.append(r"\s+")
        elif ch.isascii():
            out.append("\\" + ch)  # ASCII punctuation is escaped; RE2 rejects escaping anything else
        else:
            out.append(ch)
    return "".join(out)


def search_regex(pattern: str, regex: bool = False, whole_word: bool = False) -> str:
    """RE2 pattern for DuckDB. Plain text becomes a case- and accent-tolerant literal
    ('nacion' → 'n[aáàâãä]c[iíìîï][oóòôõö]n'), far faster than folding the text itself.
    A trailing * on a word is a prefix wildcard ('democrati*')."""
    if not pattern or not pattern.strip():
        raise ValueError("Empty search pattern")
    if regex:
        return pattern if pattern.startswith("(?") else "(?i)" + pattern
    words = pattern.strip().split()
    parts = []
    for w in words:
        star = w.endswith("*") and len(w) > 1
        parts.append(_literal(w.rstrip("*")) + (r"[\pL\pN]*" if star else ""))
    body = r"[^\pL\pN]+".join(parts) if whole_word else r"\s+".join(parts)
    if whole_word:
        body = r"(?:^|[^\pL\pN])" + body + r"(?:$|[^\pL\pN])"
    return "(?i)" + body


def parse_terms(terms: str | list[str]) -> list[dict]:
    """'a, b+c, d*' → [{label, variants:[...]}]. Commas separate series; + sums variants."""
    items = terms if isinstance(terms, list) else [t for t in terms.split(",")]
    out = []
    for item in items:
        item = item.strip()
        if not item:
            continue
        variants = [v.strip() for v in item.split("+") if v.strip()]
        for v in variants:
            if "*" in v.rstrip("*") or ("*" in v and len(v.split()) > 1):
                raise ValueError(f"'{v}': the wildcard * only works at the end of a single word")
        out.append({"label": item, "variants": variants})
    if not out:
        raise ValueError("No terms given")
    return out


# Function words, for collocations only (distinctive_words needs none: the prior handles them).
STOPWORDS = set("""
a al algo algunas algunos ante antes aquel aquella aquellas aquellos aqui así aun aunque bajo bien
cada casi como con contra cual cuales cuando de del desde donde dos e el ella ellas ello ellos en
entre era eran es esa esas ese eso esos esta estaba estado estamos estan estar estas este esto estos
fue fueron ha habia han hasta hay he la las le les lo los mas me mi mis mucho muy nada ni no nos
nosotros o os otra otras otro otros para pero poco por porque que quien quienes se sea segun ser si
sido sin sino sobre son su sus tal tambien tan tanto te tiene tienen todo todos tu un una unas uno
unos usted ustedes va vamos y ya yo señor señora señores senor senora presidente
ao aos as até à às com da das de do dos e é em entre era essa esse esta este eu foi há isso isto
já lhe mais mas me meu minha muito na nas nem no nos nós num numa o os ou para pela pelas pelo pelos
por porque quando que se sem ser seu seus sua suas são também tem têm um uma umas uns vai você
""".split())
STOPWORDS |= {fold(w) for w in STOPWORDS}
