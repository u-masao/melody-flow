"""
音楽理論に関するユーティリティ関数を提供します。
Provides utility functions related to music theory.
"""

# ルート音の名前と、C=0とする数値表現の対応表
# NOTE: 2文字のものを先に定義することで、パーサーが正しく動作するようにしています。
# Map of root note names to their numerical representation (C=0).
# NOTE: Two-character names are defined first to ensure the parser works correctly.
NOTE_MAP = {
    "C#": 1,
    "DB": 1,
    "D#": 3,
    "EB": 3,
    "F#": 6,
    "GB": 6,
    "G#": 8,
    "AB": 8,
    "A#": 10,
    "BB": 10,
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

# コード種別ごとの定義
# 'code_tone': コード構成音 (ルートからのインターバル)
# 'scales': 利用可能なペンタトニックスケール (ルートからのインターバル)
# Definitions for each chord type.
# 'code_tone': Chord constituent notes (intervals from the root).
# 'scales': Available pentatonic scales (intervals from the root).
CHORD_DEFINITIONS = {
    # Major Chords
    "": {"code_tone": [0, 4, 7], "scales": {"major_pentatonic": [0, 2, 4, 7, 9]}},
    "M7": {
        "code_tone": [0, 4, 7, 11],
        "scales": {
            "lydian_pentatonic": [0, 2, 4, 7, 11],
            "major_pentatonic_from_3rd": [2, 4, 7, 9, 11],
        },
    },
    "6": {"code_tone": [0, 4, 7, 9], "scales": {"major_pentatonic": [0, 2, 4, 7, 9]}},
    # Minor Chords
    "m": {"code_tone": [0, 3, 7], "scales": {"minor_pentatonic": [0, 3, 5, 7, 10]}},
    "m7": {
        "code_tone": [0, 3, 7, 10],
        "scales": {
            "minor_pentatonic": [0, 3, 5, 7, 10],
            "dorian_pentatonic": [0, 2, 5, 7, 10],
        },
    },
    "m6": {
        "code_tone": [0, 3, 7, 9],
        "scales": {"dorian_pentatonic": [0, 2, 5, 7, 10]},
    },
    "mM7": {
        "code_tone": [0, 3, 7, 11],
        "scales": {"melodic_minor_pentatonic": [0, 2, 3, 7, 11]},
    },
    # Dominant Chords
    "7": {
        "code_tone": [0, 4, 7, 10],
        "scales": {
            "mixolydian_pentatonic": [0, 2, 5, 7, 10],
            "altered_pentatonic_from_b7": [
                0,
                2,
                4,
                7,
                10,
            ],  # Based on Ami pentatonic over C7
        },
    },
    "7sus4": {
        "code_tone": [0, 5, 7, 10],
        "scales": {"mixolydian_pentatonic": [0, 2, 5, 7, 10]},
    },
    "7b9": {
        "code_tone": [0, 4, 7, 10], # b9はテンションとしてスケールで制御
        "scales": {
            # Cハーモニックマイナースケール由来のペンタトニック (G7b9に対して)
            "harmonic_minor_subset": [0, 1, 4, 7, 8], # G, Ab, B, D, Eb
            # G Alteredスケール由来のペンタトニック (Ab melodic minor)
            "altered_pentatonic": [1, 3, 4, 6, 10] # Ab, Bb, B, Db, F
        }
    },
    # Diminished and Half-Diminished
    "dim": {"code_tone": [0, 3, 6], "scales": {"locrian_pentatonic": [0, 3, 5, 6, 10]}},
    "dim7": {
        "code_tone": [0, 3, 6, 9],
        "scales": {"diminished_scale_subset": [0, 2, 3, 6, 9]},
    },
    "m7b5": {
        "code_tone": [0, 3, 6, 10],
        "scales": {
            "locrian_pentatonic": [0, 3, 5, 6, 10],
            "minor_pentatonic_from_4th": [
                1,
                3,
                6,
                8,
                10,
            ],  # Based on Fmi pentatonic over Cm7b5
        },
    },
    # Augmented
    "aug": {"code_tone": [0, 4, 8], "scales": {"whole_tone_subset": [0, 2, 4, 6, 8]}},
}


def parse_chord_name(chord_name: str) -> dict:
    """
    コードネーム文字列を解析し、ルート、構成音、利用可能なスケールを返します。

    Args:
        chord_name (str): 解析するコードネーム (例: "C", "Dm7", "F#aug")

    Returns:
        dict: 解析結果を含む辞書。
              {'root': int, 'code_tone': list[int], 'scales': dict}

    Raises:
        ValueError: 解析不可能なコードネームが指定された場合。
    """
    if not isinstance(chord_name, str) or not chord_name:
        raise ValueError("Input must be a non-empty string.")

    s = chord_name.replace(" ", "")

    # 1. ルート音を特定する (Find the root note)
    root_note_str = None
    root_val = -1

    # 2文字のルート音から先にチェック (Check for two-character root notes first)
    if len(s) > 1 and s[:2] in NOTE_MAP:
        root_note_str = s[:2]
        root_val = NOTE_MAP[s[:2].upper()]
    # 1文字のルート音をチェック (Then check for one-character root notes)
    elif s[0] in NOTE_MAP:
        root_note_str = s[0]
        root_val = NOTE_MAP[s[0].upper()]

    if root_note_str is None:
        raise ValueError(f"Invalid root note found in '{chord_name}'")

    # 2. コード種別を特定する (Find the chord type)
    chord_type_str = s[len(root_note_str) :]

    # Major/Minor の省略形に対応
    # Handle abbreviations for major/minor
    if chord_type_str.lower() == "maj7":
        chord_type_str = "M7"
    elif chord_type_str.lower() == "min" or chord_type_str.lower() == "minor":
        chord_type_str = "m"

    if chord_type_str not in CHORD_DEFINITIONS:
        raise ValueError(f"Invalid chord type '{chord_type_str}' in '{chord_name}'")

    chord_info = CHORD_DEFINITIONS[chord_type_str]

    return {
        "root": root_val,
        "code_tone": chord_info["code_tone"],
        "scales": chord_info["scales"],
    }


# --- 使用例 (Example Usage) ---
if __name__ == "__main__":
    test_chords = [
        "C",
        "cm",
        "Cm7",
        "CM7",
        "Dm7",
        "G7",
        "B7b9", # New test case
        "Ebm7b5",
        "F#aug",
        "BbmM7",
        "A6",
        "c#m6",
    ]

    print("--- Chord Analysis Examples ---")
    for chord in test_chords:
        try:
            result = parse_chord_name(chord)
            print(f"'{chord}':")
            print(f"  Root Note (int): {result['root']}")
            print(f"  Code Tones: {result['code_tone']}")
            print(f"  Available Scales: {result['scales']}")
            print("-" * 20)
        except ValueError as e:
            print(f"Error parsing '{chord}': {e}")
            print("-" * 20)

    print("\n--- Invalid Chord Example ---")
    try:
        parse_chord_name("Zmajor7")
    except ValueError as e:
        print(f"Correctly caught error for 'Zmajor7': {e}")
