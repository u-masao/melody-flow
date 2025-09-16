import json
import sys

from loguru import logger
from tap import Tap
import torch

# Unsloth must be imported before transformers
try:
    from unsloth import FastLanguageModel
except NotImplementedError:
    # Handle environments without GPU for testing purposes
    # The tests will mock this class anyway.
    FastLanguageModel = object

import transformers

from .melody_processor import MelodyControlLogitsProcessor, NoteTokenizer


class InferenceArgs(Tap):
    """
    MIDI生成モデルでの推論に関する設定。
    """

    model_path: str  # ファインチューニング済みモデル（LoRAアダプター）の保存先パス
    prompt: str  # 生成の元となるプロンプト。例: "Title: My Favorite Things Chords: E- Cmaj7"

    # --- 生成パラメータ ---
    max_new_tokens: int = 1024
    temperature: float = 0.8
    top_p: float = 0.9

    def configure(self):
        """引数を必須の位置引数として設定します。"""
        self.add_argument("model_path")
        self.add_argument("prompt")


class MidiGenerator:
    """
    ファインチューニングされたモデルを使ってMIDIテキストを生成するクラス。
    """

    def __init__(self, model_path: str):
        """
        モデルとトークナイザーを初期化してロードします。

        Args:
            model_path (str): ファインチューニング済みモデルのパス。
        """
        self._setup_logging()
        logger.info(f"モデルを '{model_path}' から読み込んでいます...")

        # 学習済みLoRAモデルをロード
        # Unslothが自動でベースモデルとアダプターを結合します
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=model_path,
            max_seq_length=4096,  # 学習時と同じ値を設定
            dtype=None,
            load_in_4bit=True,  # 学習時と同じ量子化設定を使用
        )
        logger.success("モデルとトークナイザーの読み込みが完了しました。")

        # 推論パイプラインの準備
        self.pipe = transformers.pipeline(
            "text-generation",
            model=self.model,
            tokenizer=self.tokenizer,
            torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
            # device="cuda",
        )

    def _setup_logging(self):
        """loguruロガーを設定します。"""
        logger.remove()
        logger.add(sys.stdout, level="INFO")

    def _format_prompt(self, prompt: str) -> str:
        """
        推論に使用する形式にプロンプトを整形します。

        Args:
            prompt (str): ユーザーからの入力プロンプト。

        Returns:
            str: モデル入力用の整形済みプロンプト。
        """
        # [INST] タグで囲み、末尾に生成開始を促すテキストを追加する
        return f"<s>[INST] {prompt} [/INST] pitch duration wait velocity instrument\n"

    def _parse_chord_progression(self, prompt: str) -> str | None:
        """
        プロンプト文字列（JSON形式を想定）からコード進行を抽出します。

        Args:
            prompt (str): ユーザーからの入力プロンプト。

        Returns:
            str | None: 抽出されたコード進行。抽出できない場合はNone。
        """
        try:
            # プロンプトは稀に末尾に ' がつくことがあるため除去
            prompt_json_str = prompt.strip().rstrip("'")
            prompt_data = json.loads(prompt_json_str)
            return prompt_data.get("chord_progression")
        except (json.JSONDecodeError, AttributeError):
            logger.warning("プロンプトからコード進行を抽出できませんでした。制約なしで生成します。")
            return None

    def _prepare_logits_processors(self, chord_progression: str | None) -> list:
        """
        コード進行に基づいてLogitsProcessorのリストを準備します。

        Args:
            chord_progression (str | None): コード進行。Noneの場合は空リストを返します。

        Returns:
            list: 生成に使用するLogitsProcessorのリスト。
        """
        if chord_progression:
            logger.info(f"コード進行 '{chord_progression}' に基づいてメロディを制約します。")
            note_tokenizer = NoteTokenizer(self.tokenizer)
            logits_processor = MelodyControlLogitsProcessor(
                chord_progression=chord_progression, note_tokenizer=note_tokenizer
            )
            return [logits_processor]
        else:
            logger.info("コード進行が指定されていないため、制約なしで生成します。")
            return []

    def _extract_result(self, generated_text: str) -> str:
        """
        モデルの出力から、生成されたMIDIテキスト部分のみを抽出します。

        Args:
            generated_text (str): モデルからの完全な出力テキスト。

        Returns:
            str: プロンプト部分を除去した、純粋な生成結果。
        """
        # [/INST] タグでプロンプトと生成部分を分割し、最後の要素を取得する
        return generated_text.split("[/INST]")[-1].strip()

    def generate(self, prompt: str, **kwargs) -> str:
        """
        プロンプトに基づいてMIDIテキストを生成するメインの関数。

        Args:
            prompt (str): 生成の元となるプロンプト。
            **kwargs: `transformers.pipeline`に渡す追加の生成パラメータ。

        Returns:
            str: 生成されたMIDIテキスト。
        """
        logger.info("推論を開始します...")
        logger.info(f"Prompt: {prompt}")

        # ステップ1: プロンプトからコード進行を抽出する
        chord_progression = self._parse_chord_progression(prompt)

        # ステップ2: コード進行に基づき、メロディを制約するプロセッサを準備する
        processors = self._prepare_logits_processors(chord_progression)

        # ステップ3: プロンプトをモデルが期待する形式に整形する
        formatted_prompt = self._format_prompt(prompt)

        # ステップ4: 整形済みプロンプトとプロセッサを使い、パイプラインでテキストを生成する
        outputs = self.pipe(
            formatted_prompt,
            do_sample=True,
            eos_token_id=self.tokenizer.eos_token_id,
            pad_token_id=self.tokenizer.pad_token_id,
            logits_processor=processors,
            **kwargs,
        )

        # ステップ5: パイプラインの出力から純粋な生成結果を抽出して返す
        result = self._extract_result(outputs[0]["generated_text"])
        logger.success("推論が完了しました。")
        return result


def main():
    """
    スクリプトのエントリーポイント。
    引数を解析し、MIDI生成を実行します。
    """
    args = InferenceArgs(
        description="ファインチューニング済みモデルでMIDIを生成するスクリプト"
    ).parse_args()

    generator = MidiGenerator(model_path=args.model_path)

    generated_midi = generator.generate(
        prompt=args.prompt,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
    )

    print("\n--- Generated MIDI data ---\n")
    print(generated_midi)


if __name__ == "__main__":
    main()
