from app.models import Category
from app.normalization import (
    normalize_author,
    normalize_book,
    normalize_subjects,
    guess_category,
    pick_best_edition,
)


class TestMissingDescription:
    def test_no_description_skips_embedding(self):
        record = normalize_book(
            title="Untitled Work",
            open_library_id="/works/OL1W",
            raw_authors="Jane Doe",
            description=None,
        )
        assert record.description is None
        assert record.embedding_text is None

    def test_blank_description_treated_as_missing(self):
        record = normalize_book(
            title="Untitled Work",
            open_library_id="/works/OL1W",
            raw_authors="Jane Doe",
            description="   ",
        )
        assert record.description is None
        assert record.embedding_text is None

    def test_dict_shaped_description_with_no_value_is_missing(self):
        record = normalize_book(
            title="Untitled Work",
            open_library_id="/works/OL1W",
            raw_authors="Jane Doe",
            description={"type": "/type/text"},
        )
        assert record.description is None
        assert record.embedding_text is None

    def test_present_description_becomes_embedding_text(self):
        record = normalize_book(
            title="Dune",
            open_library_id="/works/OL893415W",
            raw_authors="Frank Herbert",
            description="A desert planet, a prophecy, a spice.",
        )
        assert record.description == "A desert planet, a prophecy, a spice."
        assert record.embedding_text == record.description

    def test_dict_shaped_description_extracts_value(self):
        record = normalize_book(
            title="Dune",
            open_library_id="/works/OL893415W",
            raw_authors="Frank Herbert",
            description={"type": "/type/text", "value": "A desert planet."},
        )
        assert record.description == "A desert planet."
        assert record.embedding_text == "A desert planet."


class TestAuthorFormats:
    def test_single_first_last(self):
        assert normalize_author("Frank Herbert") == "Frank Herbert"

    def test_single_last_first(self):
        assert normalize_author("Tolkien, J.R.R.") == "J.R.R. Tolkien"

    def test_list_of_plain_strings(self):
        assert normalize_author(["Neil Gaiman", "Terry Pratchett"]) == "Neil Gaiman, Terry Pratchett"

    def test_list_of_dicts(self):
        raw = [{"name": "Neil Gaiman"}, {"name": "Terry Pratchett"}]
        assert normalize_author(raw) == "Neil Gaiman, Terry Pratchett"

    def test_list_of_dicts_with_last_first_names(self):
        raw = [{"name": "Gaiman, Neil"}, {"name": "Pratchett, Terry"}]
        assert normalize_author(raw) == "Neil Gaiman, Terry Pratchett"

    def test_multi_author_joined_with_and(self):
        assert normalize_author("Neil Gaiman and Terry Pratchett") == "Neil Gaiman, Terry Pratchett"

    def test_multi_author_joined_with_ampersand(self):
        assert normalize_author("Neil Gaiman & Terry Pratchett") == "Neil Gaiman, Terry Pratchett"

    def test_multi_author_joined_with_semicolon(self):
        assert normalize_author("Gaiman, Neil; Pratchett, Terry") == "Neil Gaiman, Terry Pratchett"

    def test_multi_author_already_comma_joined_first_last(self):
        # Open Library's own author_name-join convention: already "First Last"
        # names joined by commas, not one inverted "Last, First" name.
        assert normalize_author("Neil Gaiman, Terry Pratchett, Good Omens Ghost") == (
            "Neil Gaiman, Terry Pratchett, Good Omens Ghost"
        )

    def test_none_becomes_unknown(self):
        assert normalize_author(None) == "Unknown"

    def test_empty_string_becomes_unknown(self):
        assert normalize_author("   ") == "Unknown"

    def test_empty_list_becomes_unknown(self):
        assert normalize_author([]) == "Unknown"

    def test_full_normalize_book_multiple_authors(self):
        record = normalize_book(
            title="Good Omens",
            open_library_id="/works/OL262758W",
            raw_authors=[{"name": "Pratchett, Terry"}, {"name": "Gaiman, Neil"}],
        )
        assert record.author == "Terry Pratchett, Neil Gaiman"


class TestDuplicateEditions:
    def test_prefers_edition_with_both_description_and_cover(self):
        editions = [
            {"covers": [111]},
            {"description": "The one with everything.", "covers": [222]},
            {"description": "Also has a description, no cover."},
        ]
        best = pick_best_edition(editions)
        assert best["covers"] == [222]

    def test_falls_back_to_cover_only_when_no_description_available(self):
        editions = [
            {"covers": [111]},
            {},
        ]
        best = pick_best_edition(editions)
        assert best["covers"] == [111]

    def test_no_editions_returns_none(self):
        assert pick_best_edition([]) is None
        assert pick_best_edition(None) is None

    def test_normalize_book_uses_best_edition_for_missing_fields(self):
        record = normalize_book(
            title="Dune",
            open_library_id="/works/OL893415W",
            raw_authors="Frank Herbert",
            editions=[
                {"covers": [333]},
                {
                    "description": "A desert planet, a prophecy, a spice.",
                    "covers": [444],
                },
            ],
        )
        assert record.description == "A desert planet, a prophecy, a spice."
        assert record.cover_url == "https://covers.openlibrary.org/b/id/444-M.jpg"
        assert record.embedding_text is not None

    def test_normalize_book_prefers_directly_supplied_fields_over_editions(self):
        record = normalize_book(
            title="Dune",
            open_library_id="/works/OL893415W",
            raw_authors="Frank Herbert",
            cover_url="https://covers.openlibrary.org/b/id/999-M.jpg",
            description="Directly supplied description.",
            editions=[
                {"description": "Edition description.", "covers": [444]},
            ],
        )
        assert record.description == "Directly supplied description."
        assert record.cover_url == "https://covers.openlibrary.org/b/id/999-M.jpg"


class TestSubjectNormalization:
    def test_none_becomes_empty_list(self):
        assert normalize_subjects(None) == []

    def test_non_list_becomes_empty_list(self):
        assert normalize_subjects("fantasy") == []
        assert normalize_subjects({"subject": "fantasy"}) == []

    def test_lowercases_and_dedupes(self):
        raw = ["Fantasy", "fantasy", "FANTASY", "Epic Fantasy"]
        assert normalize_subjects(raw) == ["fantasy", "epic fantasy"]

    def test_drops_non_string_entries(self):
        raw = ["Fantasy", 42, None, {"nested": "dict"}, "Mystery"]
        assert normalize_subjects(raw) == ["fantasy", "mystery"]

    def test_collapses_internal_whitespace(self):
        assert normalize_subjects(["  Science   Fiction  "]) == ["science fiction"]

    def test_empty_list_stays_empty(self):
        assert normalize_subjects([]) == []


class TestGuessCategory:
    def test_matches_science_fiction(self):
        assert guess_category(["science fiction", "adventure"]) == Category.SCI_FI

    def test_matches_historical_fiction_not_generic_fiction(self):
        assert guess_category(["historical fiction"]) == Category.HISTORICAL_FICTION

    def test_matches_self_help_hyphenated_subject(self):
        assert guess_category(["self-help"]) == Category.SELF_HELP

    def test_no_match_returns_none(self):
        assert guess_category(["cooking", "travel"]) is None

    def test_empty_subjects_returns_none(self):
        assert guess_category([]) is None

    def test_normalize_book_sets_category_guess(self):
        record = normalize_book(
            title="Dune",
            open_library_id="/works/OL893415W",
            raw_authors="Frank Herbert",
            subjects=["Science Fiction", "Adventure stories"],
        )
        assert record.category_guess == Category.SCI_FI
        assert record.subjects == ["science fiction", "adventure stories"]

    def test_normalize_book_with_no_subjects_has_no_category_guess(self):
        record = normalize_book(
            title="Untitled",
            open_library_id="/works/OL2W",
            raw_authors="Jane Doe",
            subjects=None,
        )
        assert record.category_guess is None
        assert record.subjects == []
