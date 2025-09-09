from loguru import logger
import torch
from transformers import AutoTokenizer, LogitsProcessor

from .chord_name_parser import parse_chord_name
from .utils import is_arabic_numerals_only


class NoteTokenizer:
    """
    MIDIピッチ番号とモデルのトークンIDを相互変換するためのヘルパークラス。
    モデルは数値を ' 60' のような文字列トークンとして扱うため、この変換が必要です。
    """

    def __init__(self, tokenizer: AutoTokenizer):
        self.tokenizer = tokenizer
        self.pitch_to_token_id_cache: dict[int, int] = {}
        self._build_pitch_cache()

    def _build_pitch_cache(self):
        """MIDIピッチ0から127までのトークンIDを事前に計算してキャッシュします。"""
        for pitch in range(128):
            pitch_str = f"{pitch}"
            pitch_ids = self.tokenizer.encode(pitch_str, add_special_tokens=False)
            if pitch_ids:
                if len(pitch_ids) > 1:
                    logger.warning(
                        f"ピッチのトークン化が一意ではありません: {pitch_str} -> {pitch_ids}"
                    )
                self.pitch_to_token_id_cache[pitch] = pitch_ids[0]

    def pitch_to_token_id(self, pitch: int) -> int | None:
        """キャッシュから指定されたMIDIピッチに対応するトークンIDを返します。"""
        return self.pitch_to_token_id_cache.get(pitch)

    def get_pitch_scores(self, scores: torch.FloatTensor) -> torch.Tensor:
        """128個すべてのMIDIピッチのスコアを抽出します。"""
        mask = [
            self.pitch_to_token_id_cache[pitch]
            for pitch in range(128)
            if pitch in self.pitch_to_token_id_cache
        ]
        return scores[0, mask]


class MelodyControlLogitsProcessor(LogitsProcessor):
    """
    現在のコードに基づいて次の音の確率（logit）を制御するLogitsProcessor。
    """

    def __init__(
        self,
        chord: str,
        note_tokenizer: NoteTokenizer,
        penalty_ratio: float = 1.0,  # スコアの標準偏差に対する乗数
        octave_range: tuple[int, int] = (4, 7),
    ):
        self.note_tokenizer = note_tokenizer
        self.penalty_ratio = penalty_ratio
        self.octave_range = octave_range
        self.allowed_token_ids = self._get_allowed_token_ids_for_chord(chord)

    def _get_allowed_token_ids_for_chord(self, chord: str) -> set[int]:
        """指定されたコードのスケール内の音のトークンIDセットを取得します。"""
        allowed_ids = set()
        scale_notes = self._get_scale_notes_for_chord(chord)

        for octave in range(self.octave_range[0], self.octave_range[1]):
            for note_in_scale in scale_notes:
                midi_pitch = 12 * octave + note_in_scale
                if 0 <= midi_pitch < 128:
                    token_id = self.note_tokenizer.pitch_to_token_id(midi_pitch)
                    if token_id:
                        allowed_ids.add(token_id)
        return allowed_ids

    def _get_scale_notes_for_chord(self, chord: str) -> set[int]:
        """コード名を解析し、その主要なスケールの音を返します。"""
        try:
            chord_info = parse_chord_name(chord)
            # 利用可能な最初のスケールを主要なものとして使用します
            primary_scale = next(iter(chord_info["scales"].values()))
            root_note_val = chord_info["root"]
            return {(root_note_val + interval) % 12 for interval in primary_scale}
        except (ValueError, StopIteration) as e:
            logger.warning(
                f"コード '{chord}' のスケールを特定できませんでした: {e}。Cメジャーペンタトニックにフォールバックします。"
            )
            return {0, 2, 4, 7, 9}  # Cメジャーペンタトニック

    def _calculate_trend(self, sequence: str) -> tuple[int | None, int | None]:
        """シーケンスの最後のいくつかの音に基づいてピッチのトレンドを計算します。"""
        pitch_str_history = [line.split(" ")[0] for line in sequence.strip().split("\n")]

        recent_pitches = []
        last_pitch = None

        for pitch_str in pitch_str_history[-4:]:
            if is_arabic_numerals_only(pitch_str):
                pitch_val = int(pitch_str)
                recent_pitches.append(pitch_val)
                last_pitch = pitch_val

        if not recent_pitches:
            return None, None

        trend_pitch = int(sum(recent_pitches) / len(recent_pitches))
        logger.debug(f"計算されたトレンド: {trend_pitch=}, {last_pitch=}")
        return trend_pitch, last_pitch

    def __call__(
        self, input_ids: torch.LongTensor, scores: torch.FloatTensor
    ) -> torch.FloatTensor:
        """
        このメソッドは生成ループの各ステップで呼び出されます。
        `scores` テンソルを変更してメロディ生成を誘導します。
        """
        sequence = self.note_tokenizer.tokenizer.decode(input_ids[0])

        # モデルが新しい音を生成しようとするとき（改行文字の後）にのみ介入します。
        if not sequence.endswith("\n"):
            return scores

        logger.debug(f"シーケンスに制約を適用中: ...{sequence[-30:]}")

        trend_pitch, last_pitch = self._calculate_trend(sequence)

        # キャッシュからすべての可能なピッチトークンIDを取得します
        all_pitch_token_ids = set(self.note_tokenizer.pitch_to_token_id_cache.values())

        # コードスケールから許可された音で始めます
        final_allowed_ids = self.allowed_token_ids.copy()

        # トレンドが特定された場合、許可された音をさらに制約します
        if trend_pitch is not None:
            trend_ids_set = set()
            for pitch in range(trend_pitch - 5, trend_pitch + 5):
                if pitch != last_pitch:
                    token_id = self.note_tokenizer.pitch_to_token_id(pitch)
                    if token_id:
                        trend_ids_set.add(token_id)

            if trend_ids_set:
                final_allowed_ids &= trend_ids_set

        # 抑制するピッチトークンを決定します
        suppressed_pitch_ids = list(all_pitch_token_ids - final_allowed_ids)

        # 抑制されたピッチにペナルティを適用します
        if suppressed_pitch_ids:
            # スコアの標準偏差に基づいてペナルティを計算します
            pitch_score_std = self.note_tokenizer.get_pitch_scores(scores).std()
            penalty_value = pitch_score_std * self.penalty_ratio

            # ペナルティ用のテンソルを使用して、scoresと同じデバイス上にあることを保証します
            penalty = torch.zeros_like(scores)
            penalty[:, suppressed_pitch_ids] = penalty_value
            scores -= penalty

        return scores
