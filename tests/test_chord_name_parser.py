import pytest
from src.chord_name_parser import parse_chord_name


# --- 正常系のテストケース ---
@pytest.mark.parametrize(
    "chord_name, expected_root, expected_tones, expected_scales_count",
    [
        ("C", 0, [0, 4, 7], 1),
        ("Cmaj7", 0, [0, 4, 7, 11], 2),
        ("Cm", 0, [0, 3, 7], 1),
        ("Cm7", 0, [0, 3, 7, 10], 2),
        ("C7", 0, [0, 4, 7, 10], 2),
        ("G#m7b5", 8, [0, 3, 6, 10], 2),
        ("Dbaug", 1, [0, 4, 8], 1),
        ("Fdim7", 5, [0, 3, 6, 9], 1),
        ("A6", 9, [0, 4, 7, 9], 1),
        # 大文字・小文字、スペースの揺らぎを許容するかのテスト
        ("c#m", 1, [0, 3, 7], 1),
        ("eb7", 3, [0, 4, 7, 10], 2),
        (" F # dim ", 6, [0, 3, 6], 1),
    ],
)
def test_parse_chord_name_valid(
    chord_name, expected_root, expected_tones, expected_scales_count
):
    """
    正常なコードネームが正しく解析されることをテストする
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
        "Z",  # 不正なルート音
        "Hmaj7",
        "C!",  # 不正なコード種別
        "Cmaj9", # 未定義のコード
        "Gsus",
        "",  # 空文字
        None,  # None
        123,  # 文字列以外
    ],
)
def test_parse_chord_name_invalid(invalid_chord_name):
    """
    不正なコードネームに対してValueErrorが発生することをテストする
    """
    with pytest.raises(ValueError):
        parse_chord_name(invalid_chord_name)
