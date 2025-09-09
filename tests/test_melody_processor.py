import pytest
import torch
from unittest.mock import MagicMock
from transformers import AutoTokenizer

from src.model.melody_processor import MelodyControlLogitsProcessor, NoteTokenizer
from src.model.utils import is_arabic_numerals_only

# --- モックを使用したユニットテスト ---

@pytest.fixture
def mock_hf_tokenizer():
    """高速なユニットテストのためのモックHugging Faceトークナイザーのフィクスチャ。"""
    tokenizer = MagicMock()
    # 数字 "0" から "127" のトークン化をシミュレートします
    # 簡単のため、トークンID = ピッチ + 1000とします
    tokenizer.encode.side_effect = lambda s, add_special_tokens=False: [int(s.strip()) + 1000] if is_arabic_numerals_only(s.strip()) else []
    tokenizer.decode.side_effect = lambda ids: str(ids[0] - 1000)
    return tokenizer

@pytest.fixture
def note_tokenizer_mock(mock_hf_tokenizer):
    """モックHFトークナイザーで初期化されたNoteTokenizerを提供するためのフィクスチャ。"""
    return NoteTokenizer(mock_hf_tokenizer)

class TestNoteTokenizer:
    def test_pitch_cache_build(self, note_tokenizer_mock):
        """ピッチからトークンIDへのキャッシュが正しく構築されるかをテストします。"""
        assert note_tokenizer_mock.pitch_to_token_id(60) == 60 + 1000
        assert note_tokenizer_mock.pitch_to_token_id(127) == 127 + 1000
        assert note_tokenizer_mock.pitch_to_token_id(128) is None

    def test_get_pitch_scores(self, note_tokenizer_mock):
        """より大きなスコアテンソルからピッチスコアの抽出をテストします。"""
        scores = torch.randn(1, 2000)
        pitch_scores = note_tokenizer_mock.get_pitch_scores(scores)
        assert pitch_scores.shape[0] == 128
        expected_score = scores[0, 60 + 1000]
        assert pitch_scores[60] == expected_score

class TestMelodyControlLogitsProcessorUnit:
    def test_get_scale_notes_for_chord(self, note_tokenizer_mock):
        """指定されたコードのスケール音が正しく識別されるかをテストします。"""
        processor = MelodyControlLogitsProcessor("C", note_tokenizer_mock)
        c_major_pentatonic = {0, 2, 4, 7, 9}
        assert processor._get_scale_notes_for_chord("C") == c_major_pentatonic
        # 無効なコードのフォールバックをテストします
        assert processor._get_scale_notes_for_chord("InvalidChord") == c_major_pentatonic

    def test_calculate_trend(self, note_tokenizer_mock):
        """ピッチトレンド計算ロジックをテストします。"""
        processor = MelodyControlLogitsProcessor("C", note_tokenizer_mock)
        sequence = "60 1 1 1\n62 1 1 1\n64 1 1 1\n"
        trend, last_pitch = processor._calculate_trend(sequence)
        assert last_pitch == 64
        assert trend == 62

    def test_call_method_applies_penalty(self, note_tokenizer_mock):
        """__call__メソッドがモックを使用してペナルティを正しく適用するかをテストします。"""
        processor = MelodyControlLogitsProcessor("Am", note_tokenizer_mock) # Am pentatonic: {9,0,2,4,7}
        mock_input_ids = torch.LongTensor([[1]])
        note_tokenizer_mock.tokenizer.decode.return_value = "60 1 1 1\n"
        scores = torch.ones(1, 2000)
        original_scores = scores.clone()

        modified_scores = processor(mock_input_ids, scores)

        # C# (pitch=1) はAmペンタトニックスケールにないため、そのトークン(1001)はペナルティを受けるべきです
        c_sharp_token_id = 1 + 1000
        # C (pitch=0) はAmペンタトニックスケールにあるため、そのトークン(1000)はペナルティを受けないべきです
        c_token_id = 0 + 1000

        assert modified_scores[0, c_sharp_token_id] < original_scores[0, c_sharp_token_id]
        assert modified_scores[0, c_token_id] == original_scores[0, c_token_id]

    def test_call_method_does_not_trigger(self, note_tokenizer_mock):
        """シーケンスが改行で終わらない場合、プロセッサが何もしないことをテストします。"""
        processor = MelodyControlLogitsProcessor("C", note_tokenizer_mock)
        note_tokenizer_mock.tokenizer.decode.return_value = "60 1 1 1" # 改行なし
        scores = torch.ones(1, 2000)
        original_scores = scores.clone()
        modified_scores = processor(torch.LongTensor([[1]]), scores)
        assert torch.equal(modified_scores, original_scores)


# --- 実際のトークナイザーを使用した統合風テスト（元のファイルから保持） ---

@pytest.fixture(scope="module")
def real_tokenizer():
    """統合テストのためにモジュールごとに一度だけ実際のトークナイザーをロードします。"""
    return AutoTokenizer.from_pretrained("dx2102/llama-midi")

@pytest.fixture(scope="module")
def note_tokenizer_real(real_tokenizer):
    return NoteTokenizer(real_tokenizer)

@pytest.mark.parametrize(
    "chord, expected_allowed_notes",
    [
        ("C", {0, 2, 4, 7, 9}),
        ("Am", {0, 2, 4, 7, 9}),
    ],
)
def test_melody_processor_restricts_notes_integration(
    real_tokenizer, note_tokenizer_real, chord, expected_allowed_notes
):
    """
    実際のトークナイザーでスケールベースの制約が機能することを確認する統合風テスト。
    これはトークンの衝突をチェックするより複雑なテストです。
    """
    processor = MelodyControlLogitsProcessor(chord=chord, note_tokenizer=note_tokenizer_real)
    scores = torch.zeros((1, len(real_tokenizer)))
    # プロセッサをトリガーするために新しい行の開始にいることをシミュレートします
    input_ids = torch.LongTensor([real_tokenizer.encode("\n", add_special_tokens=False)])

    processed_scores = processor(input_ids, scores)

    # 既知の不許可音のスコアがペナルティを受けていることを確認します。
    # Cメジャーペンタトニックの場合、C#（ピッチ1）は不許可です。
    # Aマイナーペンタトニックの場合、A#（ピッチ10）は不許可です。
    disallowed_pitch = 1 if chord == "C" else 10
    disallowed_token_id = note_tokenizer_real.pitch_to_token_id(disallowed_pitch)

    # ペナルティは-infではなくなりましたが、ゼロ未満であるべきです
    if disallowed_token_id:
        assert processed_scores[0, disallowed_token_id] < 0

    # 既知の許可音のスコアがペナルティを受けていないことを確認します。
    # Cメジャーペンタトニックの場合、E（ピッチ4）は許可されます。
    # Aマイナーペンタトニックの場合、C（ピッチ0）は許可されます。
    allowed_pitch = 4 if chord == "C" else 0
    allowed_token_id = note_tokenizer_real.pitch_to_token_id(allowed_pitch)

    if allowed_token_id:
        assert processed_scores[0, allowed_token_id] == 0
