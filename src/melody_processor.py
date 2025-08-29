import torch
from transformers import LogitsProcessor, AutoTokenizer
from typing import List, Dict

# --- 定数 (変更なし) ---
NOTE_TO_MIDI = {
    'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5,
    'F#': 6, 'Gb': 6, 'G': 7, 'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11
}
CHORD_TO_SCALE = {
    'C': [0, 2, 4, 5, 7, 9, 11],  # C Major
    'G': [7, 9, 11, 0, 2, 4, 6],  # G Major
    'Am': [9, 11, 0, 2, 4, 5, 7], # A Minor
    'F': [5, 7, 9, 10, 0, 2, 4],  # F Major
    'Em': [4, 6, 7, 9, 11, 0, 2], # E minor
    'Dm7': [2, 4, 5, 7, 9, 11, 0], # D Dorian (common for Dm7)
    'G7': [7, 9, 11, 0, 2, 4, 5], # G Mixolydian (common for G7)
    'Cmaj7': [0, 2, 4, 5, 7, 9, 11], # C Major / Ionian
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
            # llama-midiは " 60" のようにスペース区切りの数値をトークンとして扱う
            token_str = f" {pitch}"
            # トークナイザを使って文字列からトークンIDを取得
            token_ids = self.tokenizer.encode(token_str, add_special_tokens=False)
            if token_ids:
                self.pitch_to_token_id_cache[pitch] = token_ids[0]

    def pitch_to_token_id(self, pitch: int) -> int | None:
        """キャッシュからMIDIピッチに対応するトークンIDを返す。"""
        return self.pitch_to_token_id_cache.get(pitch)

# --- 【ここまで追加】 ---


class MelodyControlLogitsProcessor(LogitsProcessor):
    """
    コード進行に基づいて、次に出現する音の確率(logit)を制御するプロセッサ。
    """
    # 【変更】tokenizer: AutoTokenizer -> note_tokenizer: NoteTokenizer
    def __init__(self, chord: str, note_tokenizer: NoteTokenizer):
        self.note_tokenizer = note_tokenizer
        self.allowed_token_ids = self._get_allowed_token_ids(chord)
        # pitchトークンが出現する最初のステップかどうかを判定するフラグ
        self.is_first_step = True

    def _get_allowed_token_ids(self, chord: str) -> List[int]:
        """コードに対応するスケール音のトークンIDリストを取得する。"""
        root_note = chord.replace('m', '').replace('7', '').replace('maj', '')
        scale = CHORD_TO_SCALE.get(root_note, CHORD_TO_SCALE['C'])
        
        allowed_ids = []
        # 3オクターブ分 (MIDI: 48-84あたり) のスケール音を許可する
        for octave in range(3, 7):
            for note_in_scale in scale:
                midi_pitch = 12 * octave + note_in_scale
                if midi_pitch < 128:
                    token_id = self.note_tokenizer.pitch_to_token_id(midi_pitch)
                    if token_id:
                        allowed_ids.append(token_id)
        return list(set(allowed_ids))

    def __call__(self, input_ids: torch.LongTensor, scores: torch.FloatTensor) -> torch.FloatTensor:
        # NOTE: このロジックは llama-midi の出力形式 'pitch duration wait velocity instrument' に依存する
        
        # 最後の改行からのトークンを取得
        sequence = self.note_tokenizer.tokenizer.decode(input_ids[0])
        last_line = sequence.strip().split('\n')[-1]
        tokens_in_line = last_line.strip().split(' ')

        # pitch, duration, wait, velocity のどれを生成している段階かを判定
        # ここでは単純化し、最初のトークン(pitch)のみを制御対象とする
        if len(tokens_in_line) == 1 and tokens_in_line[0] == "": # 改行直後
             # マスク用のテンソルを作成 (全トークンの確率を -inf に)
            mask = torch.full_like(scores, -float('inf'))
            # 許可されたトークンIDの箇所だけ確率を 0 に戻す (元の確率を維持)
            mask[:, self.allowed_token_ids] = 0
            scores = scores + mask

        return scores

