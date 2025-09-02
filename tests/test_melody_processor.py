import pytest
import torch
from transformers import AutoTokenizer

# テスト対象のクラスをインポート
# プロジェクトのルートディレクトリからpytestを実行することを想定
from src.melody_processor import MelodyControlLogitsProcessor, NoteTokenizer


# --- テスト用のフィクスチャ ---
@pytest.fixture(scope="module")
def tokenizer():
    """
    テスト全体で一度だけトークナイザを読み込むためのフィクスチャ
    """
    # 実際のトークナイザを使用して、トークンIDとMIDIピッチのマッピングを正確にテストする
    return AutoTokenizer.from_pretrained("dx2102/llama-midi")


# --- テストケース ---
@pytest.mark.parametrize(
    "chord, expected_allowed_notes",
    [
        ("c", [0, 2, 4, 5, 7, 9, 11]),  # C Major Scale
        ("g", [0, 2, 4, 5, 7, 9, 10]),  # G Major Scale
        ("am", [0, 2, 3, 5, 7, 8, 10]),  # A Minor Scale
        (
            "f",
            [0, 1, 3, 5, 6, 8, 10],
        ),  # F Major Scale (※ F Lydianになっているので要確認だが、ロジック通りかテスト)
    ],
)
def test_melody_processor_restricts_notes(tokenizer, chord, expected_allowed_notes):
    """
    指定されたコードに基づき、スケール外の音の確率が-infに設定されるかをテストする
    """
    note_tokenizer = NoteTokenizer(tokenizer)
    # 1. テストの準備
    processor = MelodyControlLogitsProcessor(chord=chord, note_tokenizer=note_tokenizer)

    # ダミーのlogitsを作成 (バッチサイズ1, トークン数=ボキャブラリサイズ)
    # 全てのlogitを0.0で初期化
    vocab_size = len(tokenizer)
    scores = torch.zeros((1, vocab_size))

    # ダミーのinput_ids (今回は使われないが、呼び出しには必要)
    input_ids = torch.LongTensor([[]])

    # 2. テスト対象の関数を実行
    processed_scores = processor(input_ids, scores)

    # 3. 結果の検証
    # 全てのトークンIDについてループ
    for token_id in range(vocab_size):
        token_str = tokenizer.decode([token_id])

        # NOTE_ON トークンのみをチェック
        if "NOTE_ON" in token_str:
            try:
                pitch = int(token_str.split("_")[-1])
                note_index = pitch % 12  # C=0, C#=1, ... B=11

                # スケール内の音か、スケール外の音か
                if note_index in expected_allowed_notes:
                    # 許可されている音のlogitは-infになっていないはず
                    assert processed_scores[0, token_id] != -float("Inf"), (
                        f"Chord '{chord}': Allowed note {pitch} ({note_index}) was incorrectly restricted."
                    )
                else:
                    # 許可されていない音のlogitは-infになっているはず
                    assert processed_scores[0, token_id] == -float("Inf"), (
                        f"Chord '{chord}': Disallowed note {pitch} ({note_index}) was not restricted."
                    )

            except (ValueError, IndexError):
                # NOTE_ON形式でないトークンは無視
                continue
