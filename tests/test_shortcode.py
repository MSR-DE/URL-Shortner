"""Unit tests for short-code generation (no database required)."""

from app.shortcode import ALPHABET, RESERVED_CODES, generate_short_code


def test_alphabet_is_base62_and_url_safe():
    assert len(ALPHABET) == 62
    assert len(set(ALPHABET)) == 62
    assert ALPHABET.isalnum()


def test_generated_code_has_the_requested_length():
    for length in (4, 7, 12):
        assert len(generate_short_code(length)) == length


def test_generated_code_uses_only_alphabet_characters():
    assert set(generate_short_code(7)) <= set(ALPHABET)


def test_generated_codes_are_not_repetitive():
    """A weak but useful smoke test: 1000 draws should be near-unique."""
    codes = {generate_short_code(7) for _ in range(1000)}
    assert len(codes) == 1000


def test_reserved_paths_are_never_returned():
    """Codes short enough to collide with a reserved word must skip it."""
    for _ in range(2000):
        assert generate_short_code(5).lower() not in RESERVED_CODES
