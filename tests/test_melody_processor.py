import pytest
from src.model.melody_processor import (
    MelodyControlLogitsProcessor,
    NoteTokenizer,
)
import torch
import torch.nn.functional as F
from transformers import PreTrainedTokenizer

# --- Mocks and Fixtures ---


# `transformers.AutoTokenizer`の挙動を模倣するモッククラス
class MockTokenizer(PreTrainedTokenizer):
    def __init__(self, **kwargs):
        self.vocab = {"<eos>": 0, "\n": 1}
        for i in range(128):
            self.vocab[str(i)] = i + 2
        self.reverse_vocab = {v: k for k, v in self.vocab.items()}

        super().__init__(eos_token="<eos>", **kwargs)

    @property
    def vocab_size(self):
        return len(self.vocab)

    def get_vocab(self):
        return self.vocab

    def _convert_token_to_id(self, token):
        return self.vocab.get(token)

    def _convert_id_to_token(self, index):
        return self.reverse_vocab.get(index)

    def _tokenize(self, text, **kwargs):
        # 改行を独立したトークンとして扱えるように修正
        processed_text = text.replace("\n", " \n ")
        return [token for token in processed_text.split(" ") if token]


@pytest.fixture(scope="module")
def mock_tokenizer():
    return MockTokenizer()


@pytest.fixture(scope="module")
def note_tokenizer(mock_tokenizer):
    return NoteTokenizer(mock_tokenizer)


# --- Test Cases ---


class TestNoteTokenizer:
    def test_build_pitch_cache(self, note_tokenizer, mock_tokenizer):
        assert len(note_tokenizer.pitch_to_token_id_cache) == 128
        assert note_tokenizer.pitch_to_token_id(60) == mock_tokenizer.vocab["60"]
        assert note_tokenizer.pitch_to_token_id(127) == mock_tokenizer.vocab["127"]
        assert len(note_tokenizer.all_pitch_token_ids) == 128

    def test_pitch_to_token_id(self, note_tokenizer):
        assert note_tokenizer.pitch_to_token_id(72) is not None
        assert note_tokenizer.pitch_to_token_id(128) is None

    def test_get_pitch_scores(self, note_tokenizer, mock_tokenizer):
        scores = torch.randn(1, mock_tokenizer.vocab_size)
        pitch_scores = note_tokenizer.get_pitch_scores(scores)
        assert pitch_scores.shape == (1, 128)

    def test_ids_to_string(self, note_tokenizer, mock_tokenizer):
        token_ids = [
            mock_tokenizer.vocab["60"],
            mock_tokenizer.vocab["64"],
            mock_tokenizer.vocab["67"],
        ]
        assert note_tokenizer.ids_to_string(token_ids) == "60 64 67"
        shuffled_ids = [
            mock_tokenizer.vocab["67"],
            mock_tokenizer.vocab["60"],
            mock_tokenizer.vocab["64"],
        ]
        assert note_tokenizer.ids_to_string(shuffled_ids) == "60 64 67"
        invalid_ids = [mock_tokenizer.vocab["60"], 9999, mock_tokenizer.vocab["64"]]
        assert note_tokenizer.ids_to_string(invalid_ids) == "60 64"


class TestMelodyControlLogitsProcessor:
    def test_get_allowed_token_ids_for_cm7(self, note_tokenizer):
        processor = MelodyControlLogitsProcessor("Cm7", note_tokenizer)
        allowed_ids = processor.allowed_token_ids
        allowed_pitches = {note_tokenizer.token_id_to_pitch_cache[tid] % 12 for tid in allowed_ids}
        assert allowed_pitches == {0, 2, 3, 5, 7, 10}

        # オクターブ範囲 (4, 7) -> MIDIピッチ 48 から 83 まで
        # 範囲内のスケール音
        assert note_tokenizer.pitch_to_token_id(48) in allowed_ids  # C4
        assert note_tokenizer.pitch_to_token_id(82) in allowed_ids  # A#6 (82 % 12 = 10)
        # 範囲内だがスケール外の音
        assert note_tokenizer.pitch_to_token_id(49) not in allowed_ids  # C#4
        assert note_tokenizer.pitch_to_token_id(83) not in allowed_ids  # B6
        # 範囲外の音
        assert note_tokenizer.pitch_to_token_id(47) not in allowed_ids  # B3
        assert note_tokenizer.pitch_to_token_id(84) not in allowed_ids  # C7
        assert note_tokenizer.pitch_to_token_id(95) not in allowed_ids  # B7

    def test_get_allowed_token_ids_for_invalid_chord(self, note_tokenizer):
        processor = MelodyControlLogitsProcessor("InvalidChord", note_tokenizer)
        allowed_ids = processor.allowed_token_ids
        allowed_pitches = {note_tokenizer.token_id_to_pitch_cache[tid] % 12 for tid in allowed_ids}
        assert allowed_pitches == {0, 2, 4, 7, 9}

    def test_parse_pitch_from_string(self, note_tokenizer):
        processor = MelodyControlLogitsProcessor("C", note_tokenizer)
        assert processor._parse_pitch_from_string("60") == 60
        assert processor._parse_pitch_from_string("0") == 0
        assert processor._parse_pitch_from_string("abc") is None
        assert processor._parse_pitch_from_string("60a") is None
        assert processor._parse_pitch_from_string("01") is None
        assert processor._parse_pitch_from_string("") is None

    def test_calculate_pitch_trend(self, note_tokenizer):
        processor = MelodyControlLogitsProcessor("C", note_tokenizer)
        sequence = "style=... chord=...\npitch duration...\n60 1 1 100\n62 1 1 100\n64 1 1 100\n"
        trend, last = processor._calculate_pitch_trend(sequence)
        assert last == 64
        assert trend == 62

    def test_call_does_not_trigger(self, note_tokenizer):
        processor = MelodyControlLogitsProcessor("C", note_tokenizer)
        token_id_60 = note_tokenizer.pitch_to_token_id(60)
        input_ids = torch.LongTensor([[token_id_60]])
        original_scores = torch.randn(1, note_tokenizer.tokenizer.vocab_size)
        scores = original_scores.clone()
        new_scores = processor(input_ids, scores)
        assert torch.equal(original_scores, new_scores)

    def test_call_applies_penalty(self, note_tokenizer):
        processor = MelodyControlLogitsProcessor("C", note_tokenizer)
        sequence = "60 1 1\n62 1 1\n64 1 1\n"
        input_ids = torch.LongTensor(
            [note_tokenizer.tokenizer.encode(sequence, add_special_tokens=False)]
        )
        scores = torch.zeros(1, note_tokenizer.tokenizer.vocab_size)
        original_scores = scores.clone()

        new_scores = processor(input_ids, scores)

        assert not torch.equal(original_scores, new_scores)

        # C Major Pentatonic (0,2,4,7,9) とトレンド [57, 67) の積集合
        # 直前の音(64)は除外 -> {57, 60, 62}
        allowed_pitches = {57, 60, 62}
        allowed_ids = {note_tokenizer.pitch_to_token_id(p) for p in allowed_pitches}

        # Logitsではなく確率(Probability)で比較する
        original_probs = F.softmax(original_scores, dim=-1)
        new_probs = F.softmax(new_scores, dim=-1)

        for token_id in note_tokenizer.all_pitch_token_ids:
            if token_id in allowed_ids:
                # 許可されたトークンは確率が上がる
                assert new_probs[0, token_id] > original_probs[0, token_id]
            else:
                # 許可されなかったトークンは確率が下がる
                assert new_probs[0, token_id] < original_probs[0, token_id]
