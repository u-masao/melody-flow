import re
from typing import ClassVar, Final

from loguru import logger
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, LogitsProcessor

from .chord_name_parser import parse_chord_name

# --- Constants ---
MIDI_PITCH_RANGE: Final[int] = 128


def decrease_tokens_probability(
    logits: torch.Tensor, token_ids: list[int], factor: float = 0.9
) -> torch.Tensor:
    """
    指定された複数のトークンIDの出現確率を、指定した係数で一括して減少させます。

    Args:
        logits (torch.Tensor): モデルから出力されたlogits (形状: [batch_size, vocab_size])
        token_ids (List[int]): 確率を操作したいトークンIDのリスト
        factor (float, optional): 元の確率に乗算する係数。デフォルトは0.9 (10%減)。

    Returns:
        torch.Tensor: 修正後のlogits
    """
    if not (0.0 <= factor < 1.0):
        raise ValueError("係数(factor)は0.0以上1.0未満である必要があります。")
    if not token_ids:
        return logits

    # 1. Logitsを確率に変換 (Softmax)
    probs = F.softmax(logits, dim=-1)

    # 2. 指定された全トークンの確率を係数で減少させる
    original_target_probs = probs[:, token_ids].clone()
    new_target_probs = original_target_probs * factor
    probs[:, token_ids] = new_target_probs

    # 3. 他のトークンの確率を再正規化
    # 変更したトークン群の、変更前後の確率の合計を計算
    sum_original_target = original_target_probs.sum(dim=-1)
    sum_new_target = new_target_probs.sum(dim=-1)

    # それ以外のトークン群の、変更前後の確率の合計を計算
    sum_original_other = 1.0 - sum_original_target
    sum_new_other = 1.0 - sum_new_target

    # ゼロ除算を防止
    sum_original_other = torch.clamp(sum_original_other, min=1e-9)

    # スケール係数を計算
    scale_factor = sum_new_other / sum_original_other

    # 他のトークンにスケールを適用
    other_tokens_mask = torch.ones_like(probs, dtype=torch.bool)
    other_tokens_mask[:, token_ids] = False

    scale_factor = scale_factor.unsqueeze(-1).expand_as(probs)
    probs[other_tokens_mask] *= scale_factor[other_tokens_mask]

    # 4. 確率をLogitsに戻す (Log)
    new_logits = torch.log(probs + 1e-9)

    return new_logits


class NoteTokenizer:
    """
    MIDIピッチ番号とモデルのトークンIDを相互変換するためのヘルパークラス。
    A helper class for converting between MIDI pitch numbers and model token IDs.
    """

    def __init__(self, tokenizer: AutoTokenizer):
        self.tokenizer = tokenizer
        self.pitch_to_token_id_cache: dict[int, int] = {}
        self.token_id_to_pitch_cache: dict[int, int] = {}
        self.all_pitch_token_ids: set[int] = set()
        self._pitch_token_id_mask: list[int] = []
        self._build_pitch_cache()

    def _build_pitch_cache(self) -> None:
        """MIDIピッチ0から127までのトークンIDを事前に計算してキャッシュする。"""
        pitch_ids = []
        for pitch in range(MIDI_PITCH_RANGE):
            pitch_str = str(pitch)
            # トークンIDが単一の数字トークンであることを確認
            # (e.g., "60" -> [token_for_60], not [token_for_6, token_for_0])
            tokens = self.tokenizer.encode(pitch_str, add_special_tokens=False)
            if len(tokens) == 1:
                token_id = tokens[0]
                self.pitch_to_token_id_cache[pitch] = token_id
                self.token_id_to_pitch_cache[token_id] = pitch
                pitch_ids.append(token_id)
            else:
                logger.warning(
                    f"Pitch '{pitch_str}' is tokenized into multiple IDs: {tokens}. Skipping."
                )
        self.all_pitch_token_ids = set(pitch_ids)
        self._pitch_token_id_mask = pitch_ids

    def pitch_to_token_id(self, pitch: int) -> int | None:
        """キャッシュからMIDIピッチに対応するトークンIDを返す。"""
        return self.pitch_to_token_id_cache.get(pitch)

    def get_pitch_scores(self, scores: torch.FloatTensor) -> torch.Tensor:
        """
        Logitスコアテンソルから、ピッチに対応するトークンのスコアのみを抽出して返す。
        Extracts and returns only the scores of pitch-corresponding
        tokens from the logit score tensor.
        """
        return scores[:, self._pitch_token_id_mask]

    def ids_to_string(self, ids: list[int]) -> str:
        """トークンIDのリストを、ソートされたピッチの文字列に変換する。"""
        pitches = [self.token_id_to_pitch_cache.get(token_id) for token_id in ids]
        valid_pitches = sorted([p for p in pitches if p is not None])
        return " ".join(map(str, valid_pitches))


class MelodyControlLogitsProcessor(LogitsProcessor):
    """
    コード進行とメロディのトレンドに基づき、次に出現する音の確率(logit)を制御するプロセッサ。
    A processor that controls the probability (logits) of the next note
    based on chord progression and melodic trends.
    """

    # --- Configuration Constants ---
    # メロディラインとして利用するMIDIノートのオクターブ範囲 (C4=60から開始)
    TARGET_OCTAVE_RANGE: ClassVar[tuple[int, int]] = (4, 7)  # (min, max_exclusive)
    # メロディトレンド計算に利用する直近の音の数
    TREND_HISTORY_COUNT: ClassVar[int] = 4
    # トレンドピッチからの許容範囲（上下）
    TREND_PITCH_RANGE: ClassVar[int] = 5

    def __init__(
        self,
        chord: str,
        note_tokenizer: NoteTokenizer,
        penalty_ratio: float = 1.0,  # スコアの標準偏差に対するペナルティの倍率
        supress_token_prob_ratio: float = 0.3,  # 許可リストにないトークンの発生確率への乗数
    ):
        self.note_tokenizer = note_tokenizer
        self.allowed_token_ids = self._get_allowed_token_ids_for_chord(chord)
        self.penalty_ratio = penalty_ratio
        self.supress_token_prob_ratio = supress_token_prob_ratio

    def _get_allowed_token_ids_for_chord(self, chord: str) -> set[int]:
        """コード名から利用可能なスケール音を特定し、対応するトークンIDのセットを返す。"""
        scale_notes = self._get_scale_notes(chord)
        allowed_ids = set()

        min_oct, max_oct = self.TARGET_OCTAVE_RANGE
        for octave in range(min_oct, max_oct):
            for note_in_scale in scale_notes:
                midi_pitch = 12 * octave + note_in_scale
                if 0 <= midi_pitch < MIDI_PITCH_RANGE:
                    token_id = self.note_tokenizer.pitch_to_token_id(midi_pitch)
                    if token_id:
                        allowed_ids.add(token_id)
        return allowed_ids

    def _get_scale_notes(self, chord: str) -> set[int]:
        """コード名を解析し、利用可能なスケール音（0-11の数値）のセットを返す。"""
        try:
            chord_info = parse_chord_name(chord)
            root_note_val = chord_info["root"]
            available_scales = chord_info["scales"]

            # Available スケールの構成音の和集合を Availableとする
            scale_notes = set()
            for available_scale in available_scales.values():
                scale_notes |= {(root_note_val + interval) % 12 for interval in available_scale}

            if not scale_notes:
                logger.warning(f"No scale found for chord '{chord}'. Defaulting.")
                return {0, 2, 4, 7, 9}  # C Major Pentatonic

            return scale_notes
        except ValueError as e:
            logger.warning(f"Error parsing '{chord}': {e}. Defaulting.")
            return {0, 2, 4, 7, 9}  # C Major Pentatonic

    def _parse_pitch_from_string(self, pitch_str: str) -> int | None:
        """生成シーケンスからピッチ文字列を安全に整数に変換する。"""
        # 0-9 で構成されたアラビア数字のみを int に変換
        if not re.fullmatch(r"[0-9]+", pitch_str) or (
            len(pitch_str) > 1 and pitch_str.startswith("0")
        ):
            return None
        return int(pitch_str)

    def _parse_pitch_history(self, sequence: str) -> list[int | None]:
        """生成シーケンスからピッチ列を取り出す"""
        pitch_history = [
            line.strip().split(" ")[0] for line in sequence.strip().split("\n") if line.strip()
        ]
        pitches = []
        for pitch_str in pitch_history[-self.TREND_HISTORY_COUNT :]:
            pitch = self._parse_pitch_from_string(pitch_str)
            if pitch is not None:
                pitches.append(pitch)
        return pitches

    def _calculate_pitch_trend(self, sequence: str) -> tuple[int | None, int | None]:
        """生成シーケンスからメロディのトレンドピッチと最後のピッチを計算する。"""
        pitches = self._parse_pitch_history(sequence)
        if not pitches:
            return None, None

        last_pitch = pitches[-1]
        trend_pitch = int(sum(pitches) / len(pitches))
        return trend_pitch, last_pitch

    def _calculate_loop_detect(self, sequence: str, loop_period=2):
        """生成シーケンスからループを検知して避けるべきピッチを返す"""
        # 履歴のパース
        pitches = self._parse_pitch_history(sequence)

        # 履歴が少ないうちはチェックなし
        if not pitches or len(pitches) < loop_period * 2:
            return None

        # ループ検知
        loop_flag = True
        for offset in range(1, 1 + loop_period):
            if pitches[-offset - loop_period] != pitches[-offset]:
                loop_flag = False
        if loop_flag is False:
            return None

        # 前の周期のピッチを返す
        return pitches[-loop_period]

    def __call__(
        self, input_ids: torch.LongTensor, scores: torch.FloatTensor
    ) -> torch.FloatTensor:
        """
        LogitsProcessorの本体。次のトークンが音名の場合に確率を操作する。
        """
        sequence = self.note_tokenizer.tokenizer.decode(input_ids[0])

        # 次に生成するのが音名 (pitch) のタイミング（改行の直後）で介入
        if not sequence.endswith("\n"):
            return scores

        # 1. メロディトレンドを計算
        trend_pitch, last_pitch = self._calculate_pitch_trend(sequence)

        # 2. コードスケールに基づく許可リストを準備
        effective_allowed_ids = self.allowed_token_ids.copy()

        # 3. トレンドに基づいて許可リストをさらに絞り込み
        if trend_pitch is not None:
            trend_ids_set = set()
            min_p = trend_pitch - self.TREND_PITCH_RANGE
            max_p = trend_pitch + self.TREND_PITCH_RANGE
            for pitch in range(min_p, max_p):
                if pitch != last_pitch:  # 直前の音は避ける
                    token_id = self.note_tokenizer.pitch_to_token_id(pitch)
                    if token_id:
                        trend_ids_set.add(token_id)
            effective_allowed_ids &= trend_ids_set

        # 4. ループ検知（周期2）
        loop_pitch = self._calculate_loop_detect(sequence, loop_period=2)
        loop_pitch_id = None
        if loop_pitch:
            loop_pitch_id = self.note_tokenizer.pitch_to_token_id(loop_pitch)
            effective_allowed_ids = effective_allowed_ids - {loop_pitch_id}

        # 5. 許可リストにない音をリストアップ
        suppressed_pitch_ids = list(
            self.note_tokenizer.all_pitch_token_ids - effective_allowed_ids
        )

        # 6. 許可リストにないピッチの発生確率を抑制
        if suppressed_pitch_ids:
            scores = decrease_tokens_probability(
                scores,
                token_ids=suppressed_pitch_ids,
                factor=self.supress_token_prob_ratio,
            )
        return scores
