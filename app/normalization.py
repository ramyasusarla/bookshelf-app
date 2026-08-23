"""Normalization layer between raw Open Library data and the DB.

Open Library's API returns inconsistent metadata: descriptions are sometimes
missing, sometimes a plain string, sometimes {"value": ...}; author data shows
up as a flat "First Last" string, a "Last, First" string, a list of strings,
or a list of {"name": ...} dicts; subject/genre tags are free-text and
inconsistently cased. normalize_book() is the single place that turns any of
that into a clean, predictable BookRecord.

Deliberately pure and synchronous — no HTTP calls happen here. Callers (in
app/open_library.py, app/recommendations.py, app/routers/books.py) do the
fetching and hand the raw shapes in, which keeps this module trivially
unit-testable without mocking network calls.
"""

from dataclasses import dataclass, field

from app.models import Category

COVER_URL = "https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"

# Open Library subject slugs, verified against the live API (checked
# work_count for each before picking) rather than guessed:
#   - REALISTIC_FICTION -> "realistic_fiction" is a real subject but thin
#     (~150 works). Open Library doesn't have a strong equivalent for this
#     school/library-style category, so this genre's candidate pool will
#     usually be small.
#   - MEMOIR -> "memoir" is real but also thin (~330 works).
#   - SELF_HELP -> Open Library has two distinct subjects here: "self-help"
#     (hyphen, ~4k works, canonical display name "self-help") and
#     "self_help" (underscore, ~700 works, display name "self help") as a
#     separate, smaller subject. Picked the larger hyphenated one.
# Everything else (fantasy, science_fiction, mystery, romance,
# historical_fiction, biography, history) mapped cleanly with large pools.
#
# This is also the controlled vocabulary normalize_subjects()/guess_category()
# map free-text Open Library subjects onto.
GENRE_SUBJECT_MAP: dict[Category, str] = {
    Category.FANTASY: "fantasy",
    Category.SCI_FI: "science_fiction",
    Category.MYSTERY: "mystery",
    Category.ROMANCE: "romance",
    Category.HISTORICAL_FICTION: "historical_fiction",
    Category.REALISTIC_FICTION: "realistic_fiction",
    Category.BIOGRAPHY: "biography",
    Category.MEMOIR: "memoir",
    Category.SELF_HELP: "self-help",
    Category.HISTORY: "history",
}

# Precomputed (category, space-separated keyword) pairs for substring
# matching against free-text subjects, e.g. "science_fiction" -> "science
# fiction" so it matches a subject string like "science fiction" or "hard
# science fiction".
_CATEGORY_KEYWORDS: list[tuple[Category, str]] = [
    (category, slug.replace("_", " ").replace("-", " "))
    for category, slug in GENRE_SUBJECT_MAP.items()
]

_MULTI_AUTHOR_SEPARATORS = (" and ", " & ", ";")


@dataclass
class BookRecord:
    title: str
    author: str
    cover_url: str | None
    open_library_id: str | None
    description: str | None
    # None signals "no usable source text" — callers must skip embedding
    # generation rather than embedding an empty/placeholder string.
    embedding_text: str | None
    subjects: list[str] = field(default_factory=list)
    category_guess: Category | None = None


def _extract_description(raw: str | dict | None) -> str | None:
    """Open Library returns a work's description as a plain string OR a
    {"value": ...} dict depending on the endpoint. Normalize both."""
    if isinstance(raw, dict):
        value = raw.get("value")
        return value.strip() if isinstance(value, str) and value.strip() else None
    if isinstance(raw, str):
        return raw.strip() or None
    return None


def _swap_if_last_first(name: str) -> str:
    """"Tolkien, J.R.R." -> "J.R.R. Tolkien". A name is only treated as
    "Last, First" when it has exactly one comma — multiple commas mean the
    string is actually a list of separate authors, not one inverted name."""
    name = name.strip()
    if name.count(",") == 1:
        last, first = (part.strip() for part in name.split(","))
        if last and first:
            return f"{first} {last}"
    return name


def normalize_author(raw: str | list[str] | list[dict] | None) -> str:
    """Standardize author formatting across every shape Open Library hands
    back: a single "First Last" string, a single "Last, First" string, "A and
    B" / "A & B" / "A; B" multi-author strings, an already-joined "A, B, C"
    string (Open Library's own author_name-join convention), a list of name
    strings, or a list of {"name": ...} dicts."""
    if raw is None:
        return "Unknown"

    if isinstance(raw, list):
        names = []
        for entry in raw:
            if isinstance(entry, dict):
                name = entry.get("name")
            else:
                name = entry
            if isinstance(name, str) and name.strip():
                names.append(_swap_if_last_first(name))
        return ", ".join(names) if names else "Unknown"

    text = raw.strip()
    if not text:
        return "Unknown"

    for separator in _MULTI_AUTHOR_SEPARATORS:
        if separator in text:
            parts = [_swap_if_last_first(p) for p in text.split(separator) if p.strip()]
            return ", ".join(parts) if parts else "Unknown"

    if text.count(",") == 1:
        return _swap_if_last_first(text)

    # Multiple commas with no other separator: already a joined list of
    # "First Last" names (Open Library's own convention), not one inverted
    # name — leave the join as-is.
    return text


def normalize_subjects(raw: list | None) -> list[str]:
    """Lowercase, dedupe (order-preserving), and drop malformed entries."""
    if not isinstance(raw, list):
        return []

    seen: set[str] = set()
    result: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            continue
        cleaned = " ".join(entry.strip().lower().split())
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


def guess_category(subjects: list[str]) -> Category | None:
    """Best-effort map from normalized free-text subjects onto the app's
    controlled Category vocabulary (the inverse of GENRE_SUBJECT_MAP)."""
    for subject in subjects:
        # Match on hyphen/underscore-insensitive text — subjects can read
        # "self-help" while the controlled keyword is "self help", etc.
        normalized_subject = subject.replace("-", " ").replace("_", " ")
        for category, keyword in _CATEGORY_KEYWORDS:
            if keyword in normalized_subject:
                return category
    return None


def pick_best_edition(editions: list[dict] | None) -> dict | None:
    """Given multiple editions of the same work, prefer the one with both a
    description and a cover image; falls back to whichever has more of the
    two, then to the first edition if none have either."""
    if not editions:
        return None

    def score(edition: dict) -> int:
        has_description = _extract_description(edition.get("description")) is not None
        has_cover = bool(edition.get("covers")) or bool(edition.get("cover_id"))
        return (2 if has_description else 0) + (1 if has_cover else 0)

    return max(editions, key=score)


def normalize_book(
    *,
    title: str,
    open_library_id: str | None = None,
    raw_authors: str | list[str] | list[dict] | None,
    cover_url: str | None = None,
    description: str | dict | None = None,
    editions: list[dict] | None = None,
    subjects: list | None = None,
) -> BookRecord:
    author = normalize_author(raw_authors)
    resolved_description = _extract_description(description)
    resolved_cover_url = cover_url

    best_edition = pick_best_edition(editions)
    if best_edition is not None:
        if resolved_description is None:
            resolved_description = _extract_description(best_edition.get("description"))
        if resolved_cover_url is None:
            covers = best_edition.get("covers") or []
            cover_id = covers[0] if covers else best_edition.get("cover_id")
            if cover_id:
                resolved_cover_url = COVER_URL.format(cover_id=cover_id)

    normalized_subjects = normalize_subjects(subjects)

    return BookRecord(
        title=title.strip(),
        author=author,
        cover_url=resolved_cover_url,
        open_library_id=open_library_id,
        description=resolved_description,
        embedding_text=resolved_description,
        subjects=normalized_subjects,
        category_guess=guess_category(normalized_subjects) if normalized_subjects else None,
    )
