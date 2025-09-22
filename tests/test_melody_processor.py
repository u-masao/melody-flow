import re

from loguru import logger
import pytest
from src.model.melody_processor import MelodyControlLogitsProcessor, NoteTokenizer
import torch
from transformers import AutoTokenizer


def is_arabic_numerals_only(s: str) -> bool:
    # 空文字列は False とする
    if not s:
        return False
    if s == "0":
        return True
    if s.startswith("0"):
        return False
    # パターン r'[0-9]+' が文字列全体にマッチするかチェック
    return re.fullmatch(r"[0-9]+", s) is not None


@pytest.fixture(scope="module")
def tokenizer():
    """テスト全体で一度だけトークナイザを読み込むためのフィクスチャ"""
    return AutoTokenizer.from_pretrained("dx2102/llama-midi")


@pytest.fixture(scope="module")
def note_tokenizer(tokenizer):
    """NoteTokenizerのフィクスチャ"""
    return NoteTokenizer(tokenizer)


@pytest.fixture(scope="module")
def token_to_pitches_map(note_tokenizer):
    """トークンIDからピッチのリストへの逆引きマップを作成するフィクスチャ"""
    mapping = {}
    for pitch, token_id in note_tokenizer.pitch_to_token_id_cache.items():
        if token_id not in mapping:
            mapping[token_id] = []
        mapping[token_id].append(pitch)
    return mapping


@pytest.mark.parametrize(
    "chord, expected_allowed_notes",
    [
        # C Major Pentatonic: C, D, E, G, A -> 0, 2, 4, 7, 9
        ("C", {0, 2, 4, 7, 9}),
        # G Major Pentatonic: G, A, B, D, E -> 7, 9, 11, 2, 4
        ("G", {2, 4, 7, 9, 11}),
        # A Minor Pentatonic: A, C, D, E, G -> 9, 0, 2, 4, 7
        ("Am", {0, 2, 4, 7, 9}),
        # Fmaj7 uses F Lydian pentatonic and a major pentatonic from the 3rd.
        # Combined notes are: {0, 2, 4, 5, 7, 9}
        ("Fmaj7", {0, 2, 4, 5, 7, 9}),
        # Dm uses D minor pentatonic. Notes are: {0, 2, 5, 7, 9}
        ("Dm", {0, 2, 5, 7, 9}),
    ],
)
def test_melody_processor_restricts_notes(
    tokenizer, note_tokenizer, token_to_pitches_map, chord, expected_allowed_notes
):
    """
    指定されたコードに基づき、スケール外の音の確率が-infに設定されるかをテストする
    """
    processor = MelodyControlLogitsProcessor(chord=chord, note_tokenizer=note_tokenizer)

    scores = torch.zeros((1, len(tokenizer)))
    input_ids = torch.LongTensor([tokenizer.encode("\n", add_special_tokens=False)])
    logger.info(f"{input_ids=}")
    processed_scores = processor(input_ids, scores)
    logger.info(f"{scores.sum()=}")
    logger.info(f"{processed_scores.sum()=}")
    logger.info(f"{processed_scores[:100]=}")
    logger.info(f"{processed_scores.shape=}")
    logger.info(f"{(processed_scores==0).sum()=}")
    logger.info(f"{(processed_scores==-float('inf')).sum()=}")
    logger.info(f"{expected_allowed_notes=}")

    for token_id in range(len(tokenizer)):
        token_str = tokenizer.decode([token_id], skip_special_tokens=True)

        if is_arabic_numerals_only(token_str):
            pitch = int(token_str.strip())
            if 48 <= pitch <= 84:
                note_index = pitch % 12

                # logger.info(f"{pitch=}, {note_index=}")
                if note_index in expected_allowed_notes:
                    assert processed_scores[0, token_id] == 0, (
                        f"Chord '{chord}': Allowed note {pitch} "
                        f"({note_index}) was incorrectly restricted. "
                        f"Logit was {processed_scores[0, token_id]}."
                    )
                else:  # Disallowed note
                    logger.info(
                        f"disallowed: {scores[0, token_id]} -> {processed_scores[0, token_id]}"
                    )
                    if processed_scores[0, token_id] != scores[0, token_id]:
                        # トークンが抑制されていない場合、トークン衝突が原因かチェックする
                        colliding_pitches = token_to_pitches_map.get(token_id, [])
                        colliding_notes = {p % 12 for p in colliding_pitches}

                        # このトークンが表す音の中に、許可されたスケール音が含まれていないか？
                        if not colliding_notes.intersection(expected_allowed_notes):
                            # 含まれていない場合、これは真の失敗
                            pytest.fail(
                                f"Chord '{chord}': Disallowed note {pitch} ({note_index}) "
                                "with token "
                                f"{token_id} was not restricted, "
                                "and no other pitch for this token is in the allowed scale "
                                f"{expected_allowed_notes}. "
                                f"Colliding notes were {colliding_notes}. "
                                f"Logit was {processed_scores[0, token_id]}."
                            )
                        # else: 含まれている場合、衝突により抑制されなかったのは許容される挙動
        elif processed_scores[0, token_id] != 0:
            # ピッチ以外のトークンは変更されてはいけない
            if token_id in token_to_pitches_map:
                # This is a pitch token, but not in the 48-84 range. It should be suppressed.
                if processed_scores[0, token_id] != -float("inf"):
                    colliding_pitches = token_to_pitches_map.get(token_id, [])
                    colliding_notes = {p % 12 for p in colliding_pitches}
                    if not colliding_notes.intersection(expected_allowed_notes):
                        pytest.fail(f"Out-of-range pitch token {token_id} was not restricted.")
            else:
                # This is a non-pitch token and should be untouched.
                assert processed_scores[0, token_id] == 0, (
                    f"Non-pitch token '{tokenizer.decode([token_id])}' "
                    f"(ID: {token_id}) was incorrectly modified to "
                    f"{processed_scores[0, token_id]}."
                )
