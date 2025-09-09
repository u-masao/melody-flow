import re

def is_arabic_numerals_only(s: str) -> bool:
    """
    文字列がアラビア数字のみで構成され、標準的な整数のルール
    （例：'0'でない限り先頭に0がない）に従っているかを確認します。

    Args:
        s (str): 確認する文字列。

    Returns:
        bool: 文字列が有効な整数表現である場合はTrue、そうでない場合はFalse。
    """
    # 空文字列は有効な数値とは見なされません。
    if not s:
        return False
    # '0'は有効なケースです。
    if s == "0":
        return True
    # 標準的な整数には先頭に0は付きません。
    if s.startswith("0"):
        return False
    # パターン r'[0-9]+' が文字列全体にマッチする必要があります。
    return re.fullmatch(r"[0-9]+", s) is not None
