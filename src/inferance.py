import sys
import torch
from loguru import logger
from unsloth import FastLanguageModel
from tap import Tap
import transformers

class InferenceArgs(Tap):
    """
    MIDI生成モデルでの推論に関する設定。
    """
    model_path: str  # ファインチューニング済みモデル（LoRAアダプター）の保存先パス
    prompt: str      # 生成の元となるプロンプト。例: "Title: My Favorite Things Chords: E- Cmaj7"
    
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
            load_in_4bit=True,    # 学習時と同じ量子化設定を使用
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

    def generate(self, prompt: str, **kwargs) -> str:
        """
        プロンプトに基づいてMIDIテキストを生成します。

        Args:
            prompt (str): 生成の元となるプロンプト。
            **kwargs: `transformers.pipeline`に渡す生成パラメータ。

        Returns:
            str: 生成されたMIDIテキスト。
        """
        # 学習データと同じ形式のプロンプトを作成
        formatted_prompt = (
            f"<s>[INST] {prompt} [/INST] pitch duration wait velocity instrument\n"
        )
        
        logger.info("推論を開始します...")
        logger.info(f"Prompt: {prompt}")

        # パイプラインを使用してテキストを生成
        outputs = self.pipe(
            formatted_prompt,
            do_sample=True,
            eos_token_id=self.tokenizer.eos_token_id,
            pad_token_id=self.tokenizer.pad_token_id,
            **kwargs,
        )
        
        generated_text = outputs[0]['generated_text']
        
        # プロンプト部分を除去し、生成された部分のみを抽出
        result = generated_text.split("[/INST]")[-1].strip()
        
        logger.success("推論が完了しました。")
        return result


def main():
    """
    スクリプトのエントリーポイント。
    引数を解析し、MIDI生成を実行します。
    """
    args = InferenceArgs(description="ファインチューニング済みモデルでMIDIを生成するスクリプト").parse_args()

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
