import torch
from loguru import logger
from transformers import LogitsProcessor, AutoTokenizer

from typing import List, Dict

# --- 定数 (変更なし) ---
NOTE_TO_MIDI = {
    "C": 0,
    "C#": 1,
    "Db": 1,
    "D": 2,
    "D#": 3,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "Gb": 6,
    "G": 7,
    "G#": 8,
    "Ab": 8,
    "A": 9,
    "A#": 10,
    "Bb": 10,
    "B": 11,
}
CHORD_TO_SCALE = {
    "C": [0, 2, 4, 5, 7, 9, 11],  # C Major
    "G": [7, 9, 11, 0, 2, 4, 6],  # G Major
    "Am": [9, 11, 0, 2, 4, 5, 7],  # A Minor
    "F": [5, 7, 9, 10, 0, 2, 4],  # F Major
    "Em": [4, 6, 7, 9, 11, 0, 2],  # E minor
    "Dm7": [2, 4, 5, 7, 9, 11, 0],  # D Dorian (common for Dm7)
    "G7": [7, 9, 11, 0, 2, 4, 5],  # G Mixolydian (common for G7)
    "Cmaj7": [0, 2, 4, 5, 7, 9, 11],  # C Major / Ionian
}

# --- 【ここから追加】 ---


class NoteTokenizer:
    """
    MIDIピッチ番号とモデルのトークンIDを相互変換するためのヘルパークラス。
    モデルは数値を ' 60' のような文字列トークンとして扱うため、この変換処理が必要。
    """

    def __init__(self, tokenizer: AutoTokenizer):
        self.tokenizer = tokenizer
        self.pitch_to_token_id_cache: Dict[int, int] = {}
        self._build_pitch_cache()

    def _build_pitch_cache(self):
        """MIDIピッチ0から127までのトークンIDを事前に計算してキャッシュする。"""
        for pitch in range(128):
            # llama-midiは "\n60 " のようにスペース区切りの数値をトークンとして扱う
            token_str = f"{pitch}"
            # トークナイザを使って文字列からトークンIDを取得
            token_ids = self.tokenizer.encode(token_str, add_special_tokens=False)
            if token_ids:
                self.pitch_to_token_id_cache[pitch] = token_ids[0]
                if len(token_ids) > 1:
                    logger.warning(f"ピッチのトークンが一つじゃないです: {token_ids}")

    def pitch_to_token_id(self, pitch: int) -> int | None:
        """キャッシュからMIDIピッチに対応するトークンIDを返す。"""
        return self.pitch_to_token_id_cache.get(pitch)


# --- 【ここまで追加】 ---


class MelodyControlLogitsProcessor(LogitsProcessor):
    """
    コード進行に基づいて、次に出現する音の確率(logit)を制御するプロセッサ。
    """

    def __init__(self, chord: str, note_tokenizer: NoteTokenizer):
        self.note_tokenizer = note_tokenizer
        self.allowed_token_ids = self._get_allowed_token_ids(chord)

    def _get_allowed_token_ids(self, chord: str) -> List[int]:
        """コード進行に含まれるすべてのコードのスケール音のトークンIDリストを取得する。"""
        allowed_ids = set()
        # 'Cmaj7' -> 'C', 'Am' -> 'A' のようにルート音を抽出
        root_note = chord.replace("m", "").replace("7", "").replace("maj", "")
        scale = CHORD_TO_SCALE.get(
            root_note, CHORD_TO_SCALE.get(chord)
        )  # 'Am' のようなケースに対応
        if not scale:
            logger.warning(
                f"Warning: Chord '{chord}' not found in CHORD_TO_SCALE map. use C maijor."
            )
            scale = CHORD_TO_SCALE["C"]

        # 3オクターブ分 (MIDI: 48-84あたり) のスケール音を許可する
        for octave in range(4, 7):
            for note_in_scale in scale:
                midi_pitch = 12 * octave + note_in_scale
                if midi_pitch < 128:
                    token_id = self.note_tokenizer.pitch_to_token_id(midi_pitch)
                    if token_id:
                        allowed_ids.add(token_id)

        logger.info(f"{chord}: {scale=}")
        logger.info(f"{allowed_ids=}")
        return list(allowed_ids)

    def __call__(
        self, input_ids: torch.LongTensor, scores: torch.FloatTensor
    ) -> torch.FloatTensor:
        # NOTE: This logic depends on the model's output format: 'pitch duration wait velocity instrument\n'

        # Decode the generated token IDs to a string. Don't skip special tokens or strip spaces.
        sequence = self.note_tokenizer.tokenizer.decode(input_ids[0])

        # We constrain the 'pitch' token, which is the first token on a new line.
        # A new line is indicated by the previous token being a newline character.
        # So, we check if the decoded sequence ends with a newline.
        if sequence.endswith("\n"):
            logger.info(sequence)
            logger.info(scores.shape)
            # Create a mask to suppress all tokens by default.
            mask = torch.full_like(scores, -float("inf"))
            # Allow only the tokens that correspond to the pitches in our scale.
            mask[:, self.allowed_token_ids] = 0
            scores = scores + mask

        return scores
