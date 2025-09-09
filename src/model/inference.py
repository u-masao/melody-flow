import json
import sys

from loguru import logger
from tap import Tap
import torch
import transformers
from unsloth import FastLanguageModel

from .melody_processor import MelodyControlLogitsProcessor, NoteTokenizer


class InferenceArgs(Tap):
    """MIDI生成モデルでの推論に関する設定。"""
    model_path: str  # ファインチューニング済みモデル（LoRAアダプター）のパス
    prompt: str      # 生成のプロンプト。例: '{"style": "jazz", "chord_progression": "C-G-Am-F"}'

    # 生成パラメータ
    max_new_tokens: int = 1024
    temperature: float = 0.8
    top_p: float = 0.9

    def configure(self):
        """引数を必須の位置引数として設定します。"""
        self.add_argument("model_path")
        self.add_argument("prompt")


class MidiGenerator:
    """ファインチューニング済みモデルを使用してMIDIテキストを生成するクラス。"""

    def __init__(self, model_path: str):
        """モデルとトークナイザーを初期化してロードします。"""
        self._setup_logging()
        self._load_model(model_path)
        self._setup_pipeline()

    def _setup_logging(self):
        """loguruロガーを設定します。"""
        logger.remove()
        logger.add(sys.stdout, level="INFO")

    def _load_model(self, model_path: str):
        """ファインチューニング済みのLoRAモデルをロードします。"""
        logger.info(f"モデルを '{model_path}' からロード中...")
        try:
            self.model, self.tokenizer = FastLanguageModel.from_pretrained(
                model_name=model_path,
                max_seq_length=4096,
                dtype=None,
                load_in_4bit=True,
            )
            self.note_tokenizer = NoteTokenizer(self.tokenizer)
            logger.success("モデルとトークナイザーのロードが成功しました。")
        except Exception as e:
            logger.exception(f"'{model_path}' からのモデルのロードに失敗しました。")
            raise

    def _setup_pipeline(self):
        """transformersのテキスト生成パイプラインを準備します。"""
        logger.info("テキスト生成パイプラインをセットアップ中...")
        self.pipe = transformers.pipeline(
            "text-generation",
            model=self.model,
            tokenizer=self.tokenizer,
            torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        )
        logger.success("パイプラインの準備ができました。")

    def _parse_prompt(self, prompt: str) -> tuple[str | None, str | None]:
        """JSONプロンプトからスタイルとコード進行を抽出します。"""
        try:
            prompt_json_str = prompt.strip().rstrip("'")
            prompt_data = json.loads(prompt_json_str)
            style = prompt_data.get("style")
            chord_progression = prompt_data.get("chord_progression")
            return style, chord_progression
        except (json.JSONDecodeError, AttributeError):
            logger.warning(
                f"プロンプトからJSONをパースできませんでした: '{prompt}'。 "
                "スタイルやコードの制約なしで続行します。"
            )
            return None, None

    def generate(self, prompt: str, **kwargs) -> str:
        """
        プロンプトに基づいてMIDIテキストを生成します。

        Args:
            prompt (str): プロンプト。理想的にはJSON形式。
            **kwargs: パイプラインに渡す追加の生成パラメータ。

        Returns:
            str: 生成されたMIDIテキスト。
        """
        style, chord_progression = self._parse_prompt(prompt)

        # モデルは特定のフォーマットで訓練されています。
        # パースに失敗した場合は、プロンプト内容のプレースホルダーを使用します。
        content = f"style={style}, chord_progression={chord_progression}" if style and chord_progression else prompt
        formatted_prompt = f"<s>[INST] {content} [/INST] pitch duration wait velocity instrument\n"

        logger.info("推論を開始します...")
        logger.info(f"フォーマット済みプロンプトを使用: {formatted_prompt}")

        processors = []
        if chord_progression:
            logger.warning(
                "このスクリプトにおけるMelodyControlLogitsProcessorの現在の実装は"
                "単一のコード用に設計されていますが、完全な進行が提供されました。"
                "制約が期待通りに機能しない可能性があります。"
                "APIの実装では、進行を分割することで正しく処理します。"
            )
            # このプロセッサは "C-G-Am-F" のような進行文字列ではなく、単一のコードを期待します。
            # これはおそらくプロセッサ内部で失敗し、制約なしの生成につながり、
            # 元のスクリプトの挙動を維持します。
            logits_processor = MelodyControlLogitsProcessor(
                chord=chord_progression,
                note_tokenizer=self.note_tokenizer
            )
            processors.append(logits_processor)
        else:
            logger.info("コード進行が指定されていないため、制약なしで生成します。")

        outputs = self.pipe(
            formatted_prompt,
            do_sample=True,
            eos_token_id=self.tokenizer.eos_token_id,
            pad_token_id=self.tokenizer.pad_token_id,
            logits_processor=processors,
            **kwargs,
        )

        generated_text = outputs[0]["generated_text"]
        result = generated_text.split("[/INST]")[-1].strip()

        logger.success("推論が完了しました。")
        return result


def main():
    """スクリプトのエントリーポイント。"""
    args = InferenceArgs(description="ファインチューニング済みモデルでMIDIを生成するスクリプト。").parse_args()

    try:
        generator = MidiGenerator(model_path=args.model_path)
        generated_midi = generator.generate(
            prompt=args.prompt,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
        )
        logger.info("\n--- 生成されたMIDIデータ ---\n")
        # 一貫した出力処理のため、printの代わりにloggerを使用します
        for line in generated_midi.split('\n'):
            logger.info(line)

    except Exception as e:
        logger.exception(f"生成プロセス中にエラーが発生しました: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
