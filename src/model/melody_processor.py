import re

from loguru import logger
import torch
from transformers import AutoTokenizer, LogitsProcessor

from .chord_name_parser import parse_chord_name


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


class NoteTokenizer:
    """
    MIDIピッチ番号とモデルのトークンIDを相互変換するためのヘルパークラス。
    """

    def __init__(self, tokenizer: AutoTokenizer):
        self.tokenizer = tokenizer
        self.pitch_to_token_id_cache: dict[int, int] = {}
        self._build_pitch_cache()

    def _build_pitch_cache(self):
        """MIDIピッチ0から127までのトークンIDを事前に計算してキャッシュする。"""
        for pitch in range(128):
            # ピッチの文字列を取得
            pitch_str = f"{pitch}"
            # トークナイザを使って文字列からトークンIDを取得
            pitch_ids = self.tokenizer.encode(pitch_str, add_special_tokens=False)
            if pitch_ids:
                self.pitch_to_token_id_cache[pitch] = pitch_ids[0]
                if len(pitch_ids) > 1:
                    logger.warning(
                        f"ピッチのトークンが一つじゃないです: {pitch_str}-> {pitch_ids}"
                    )

    def pitch_to_token_id(self, pitch: int) -> int | None:
        """キャッシュからMIDIピッチに対応するトークンIDを返す。"""
        return self.pitch_to_token_id_cache.get(pitch)

    def get_pitch_scores(self, scores: torch.FloatTensor) -> list[float]:
        mask = []
        for pitch in range(128):
            mask.append(self.pitch_to_token_id_cache[pitch])
        return scores[0, mask]

    def ids_to_string(self, ids: list[int]) -> str:
        pitchs = []
        for x in ids:
            pitchs.append(int(self.tokenizer.decode([x])))
        return " ".join([str(x) for x in sorted(pitchs)])


class MelodyControlLogitsProcessor(LogitsProcessor):
    """
    コード進行に基づいて、次に出現する音の確率(logit)を制御するプロセッサ。
    """

    def __init__(
        self,
        chord: str,
        note_tokenizer: NoteTokenizer,
        penalty_ratio: float = 1.0,  # スコアの標準偏差に対する倍率
    ):
        self.note_tokenizer = note_tokenizer
        self.allowed_token_ids = self._get_allowed_token_ids(chord)
        self.penalty_ratio = penalty_ratio

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
                # 最初のスケールだけを利用
                break

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

        # 4オクターブ分 (MIDI: 48 - 84 あたり) の音を許可する
        for octave in range(4, 7):
            for note_in_scale in scale_notes:
                midi_pitch = 12 * octave + note_in_scale
                if 0 <= midi_pitch < 128:
                    token_id = self.note_tokenizer.pitch_to_token_id(midi_pitch)
                    if token_id:
                        allowed_ids.add(token_id)

        return list(allowed_ids)

    def __call__(
        self, input_ids: torch.LongTensor, scores: torch.FloatTensor
    ) -> torch.FloatTensor:
        # 入力は今まで生成したトークン列、次に生成する各トークンのスコア
        # input_ids は [batch, tokens], batch = 1 のみをサポート
        # scores は len(tokenizer) の長さを持つ
        sequence = self.note_tokenizer.tokenizer.decode(input_ids[0])

        # 改行の直後に次のノートを生成するため、過去のトークン列の最後が改行
        # になった際に scores に介入する
        if sequence.endswith("\n"):
            # 各ノートのスコアを出力
            # logger.info(self.note_tokenizer.get_pitch_scores(scores))
            logger.debug(sequence)

            # トレンドを計算
            def calc_trend(sequence):
                pitch_str_history = [line.split(" ")[0] for line in sequence.split("\n")]
                pitchs = []
                last_pitch = None
                trend_pitch = None
                for pitch_str in pitch_str_history[-4:]:
                    if is_arabic_numerals_only(pitch_str):
                        pitchs.append(int(pitch_str))
                        last_pitch = int(pitch_str)
                if pitchs:
                    trend_pitch = int(sum(pitchs) / len(pitchs))

                logger.debug(f"{trend_pitch=}")
                logger.debug(f"{last_pitch=}")
                return trend_pitch, last_pitch

            # トレンドを取得
            trend_pitch, last_pitch = calc_trend(sequence)
            trend_ids_set = set()

            # 生成時の制約を作成
            if trend_pitch:
                for pitch in range(trend_pitch - 5, trend_pitch + 5):
                    if pitch != last_pitch:
                        trend_ids_set.add(self.note_tokenizer.pitch_to_token_id(pitch))
            logger.debug(f"{trend_ids_set=}")

            # ピッチトークンを取得
            all_pitch_token_ids = set(self.note_tokenizer.pitch_to_token_id_cache.values())

            # 許可された id の集合を作成
            allowed_token_ids_set = set(self.allowed_token_ids)

            # 許可された id の集合とトレンドの積集合
            if trend_ids_set:
                allowed_token_ids_set = trend_ids_set & allowed_token_ids_set

            # 抑制する id のリストを作成
            suppressed_pitch_ids = [
                token_id
                for token_id in all_pitch_token_ids
                if token_id not in allowed_token_ids_set
            ]

            # ペナルティを入れる変数を初期化
            penalty = torch.zeros_like(scores)

            # 抑制する id に対してペナルティを加算
            if suppressed_pitch_ids:
                # 全てのノートのスコアの標準偏差を取得
                pitch_score_std = self.note_tokenizer.get_pitch_scores(scores).std()
                penalty[:, suppressed_pitch_ids] = pitch_score_std * self.penalty_ratio

            scores -= penalty

        return scores
