from loguru import logger
from src.chord_name_parser import parse_chord_name
import torch
from transformers import AutoTokenizer, LogitsProcessor

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


# --- 【ここから追加】 ---


class NoteTokenizer:
    """
    MIDIピッチ番号とモデルのトークンIDを相互変換するためのヘルパークラス。
    モデルは数値を ' 60' のような文字列トークンとして扱うため、この変換処理が必要。
    """

    def __init__(self, tokenizer: AutoTokenizer):
        self.tokenizer = tokenizer
        self.pitch_to_token_id_cache: dict[int, int] = {}
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

    def _get_allowed_token_ids(self, chord: str) -> list[int]:
        """コード進行に含まれるすべてのコードのスケール音のトークンIDリストを取得する。"""
        allowed_ids = set()
        scale_notes = set()

        try:
            # コード名を解析して、ルート音と利用可能なスケールを取得
            chord_info = parse_chord_name(chord)
            root_note_val = chord_info["root"]
            available_scales = chord_info["scales"]

            # 利用可能なすべてのスケールの音をセットに追加
            for scale_intervals in available_scales.values():
                for interval in scale_intervals:
                    # ルート音からのインターバルを実際のノートナンバーに変換 (mod 12)
                    note = (root_note_val + interval) % 12
                    scale_notes.add(note)

        except ValueError as e:
            logger.warning(
                f"Error parsing chord '{chord}': {e}. Defaulting to C major pentatonic."
            )
            # エラー時はCメジャーペンタトニックスケールを使用
            scale_notes = {0, 2, 4, 7, 9}

        if not scale_notes:
            logger.warning(
                f"No scale found for chord '{chord}'. Defaulting to C major pentatonic."
            )
            scale_notes = {0, 2, 4, 7, 9}

        # 4オクターブ分 (MIDI: 48-95あたり) のスケール音を許可する
        for octave in range(4, 8):
            for note_in_scale in scale_notes:
                midi_pitch = 12 * octave + note_in_scale
                if midi_pitch < 128:
                    token_id = self.note_tokenizer.pitch_to_token_id(midi_pitch)
                    if token_id:
                        allowed_ids.add(token_id)

        return list(allowed_ids)

    def __call__(
        self, input_ids: torch.LongTensor, scores: torch.FloatTensor
    ) -> torch.FloatTensor:
        # NOTE: This logic depends on the model's output format:
        # 'pitch duration wait velocity instrument\n'
        # Decode the generated token IDs to a string.
        # Don't skip special tokens or strip spaces.
        sequence = self.note_tokenizer.tokenizer.decode(input_ids[0])

        # We constrain the 'pitch' token, which is the first token on a new line.
        # A new line is indicated by the previous token being a newline character.
        # So, we check if the decoded sequence ends with a newline.
        if sequence.endswith("\n"):
            # Create a mask of zeros.
            mask = torch.zeros_like(scores)

            # Get all possible pitch token IDs from the tokenizer cache.
            all_pitch_token_ids = set(self.note_tokenizer.pitch_to_token_id_cache.values())

            def ids_to_string(ids: list[int]):
                pitchs = []
                for x in ids:
                    pitchs.append(int(self.note_tokenizer.tokenizer.decode([x])))
                return " ".join([str(x) for x in sorted(pitchs)])

            # Identify the pitch tokens that should be suppressed.
            # These are the pitch tokens not in the allowed list.
            allowed_token_ids_set = set(self.allowed_token_ids)

            suppressed_pitch_ids = [
                token_id
                for token_id in all_pitch_token_ids
                if token_id not in allowed_token_ids_set
            ]

            # Set the logits for the suppressed pitches to -inf.
            if suppressed_pitch_ids:
                mask[:, suppressed_pitch_ids] = -float("inf")

            scores = scores + mask

        return scores
