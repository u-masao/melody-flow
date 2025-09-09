import pytest
from src.model.chord_name_parser import parse_chord_name


# --- 正常系のテストケース ---
@pytest.mark.parametrize(
    "chord_name, expected_root, expected_tones, expected_scales_count",
    [
        # Basic Chords
        ("C", 0, [0, 4, 7], 1),
        ("Cm", 0, [0, 3, 7], 1),
        # 7th Chords
        ("Cmaj7", 0, [0, 4, 7, 11], 2),
        ("Cm7", 0, [0, 3, 7, 10], 2),
        ("C7", 0, [0, 4, 7, 10], 2),
        # Diminished and Augmented
        ("G#m7b5", 8, [0, 3, 6, 10], 2),
        ("Dbaug", 1, [0, 4, 8], 1),
        ("Fdim7", 5, [0, 3, 6, 9], 1),
        # Other chord types
        ("A6", 9, [0, 4, 7, 9], 1),
        # Case and space variations
        ("c#m", 1, [0, 3, 7], 1),
        ("eb7", 3, [0, 4, 7, 10], 2),
        (" F # dim ", 6, [0, 3, 6], 1),
        # Complex tension chords from original script
        ("C7(b9)", 0, [0, 4, 7, 10], 2), # maps to C7b9
        ("G7(b9,b13)", 7, [0, 4, 7, 10], 1), # maps to G7b9b13
        ("Fm7", 5, [0, 3, 7, 10], 2),
        ("F#dim7", 6, [0, 3, 6, 9], 1),
        ("Ab7", 8, [0, 4, 7, 10], 2),
        ("Dm7b5", 2, [0, 3, 6, 10], 2),
    ],
)
def test_parse_chord_name_valid(
    chord_name, expected_root, expected_tones, expected_scales_count
):
    """
    Tests that valid chord names are parsed correctly.
    """
    result = parse_chord_name(chord_name)
    assert result["root"] == expected_root
    assert result["code_tone"] == expected_tones
    assert isinstance(result["scales"], dict)
    assert len(result["scales"]) == expected_scales_count


# --- 異常系のテストケース ---
@pytest.mark.parametrize(
    "invalid_chord_name",
    [
        "Z",      # Invalid root note
        "Hmaj7",
        "C!",     # Invalid chord type
        "Cmaj9",  # Undefined chord
        "Gsus",
        "",       # Empty string
        None,     # None input
        123,      # Non-string input
    ],
)
def test_parse_chord_name_invalid(invalid_chord_name):
    """
    Tests that a ValueError is raised for invalid chord names.
    """
    with pytest.raises(ValueError):
        parse_chord_name(invalid_chord_name)
