import sys
import torch
from loguru import logger
from unsloth import FastLanguageModel
import mlflow
from datasets import load_dataset
from transformers import TrainingArguments
from trl import SFTTrainer
from tap import Tap


class MidiFinetuningExperiment:
    """
    MIDI生成モデルのファインチューニング実験を管理するクラス。
    """
    def __init__(self, config: dict):
        """
        実験の設定を初期化します。

        Args:
            config (dict): 実験のハイパーパラメータやパスを含む設定辞書。
        """
        self.config = config
        self.model = None
        self.tokenizer = None
        self._setup_logging()

    def _setup_logging(self):
        """
        loguruロガーを設定します。
        """
        logger.remove()
        logger.add(sys.stdout, level="INFO")
        logger.info("ロガーをセットアップしました。")

    def _load_model_and_tokenizer(self):
        """
        事前学習済みモデルとトークナイザーを読み込みます。
        """
        logger.info(f"モデル '{self.config['model_name']}' を読み込んでいます...")
        self.model, self.tokenizer = FastLanguageModel.from_pretrained(
            model_name=self.config['model_name'],
            max_seq_length=self.config['max_seq_length'],
            dtype=None,  # 自動選択
            load_in_4bit=self.config.get('load_in_4bit', True),
        )
        logger.success("モデルとトークナイザーの読み込みが完了しました。")

    def _apply_lora(self):
        """
        モデルにLoRAを適用します。
        """
        logger.info("モデルにLoRAアダプターを適用しています...")
        lora_config = self.config['lora']
        self.model = FastLanguageModel.get_peft_model(
            self.model,
            r=lora_config['r'],
            target_modules=lora_config['target_modules'],
            lora_alpha=lora_config['alpha'],
            lora_dropout=lora_config.get('dropout', 0),
            bias="none",
            use_gradient_checkpointing=True,
            random_state=self.config.get('seed', 42),
        )
        logger.success("LoRAの適用が完了しました。")

    def _load_dataset(self):
        """
        学習用データセットを読み込みます。
        """
        logger.info(f"データセットを '{self.config['input_data_path']}' から読み込んでいます...")
        try:
            dataset = load_dataset("json", data_files=self.config['input_data_path'], split="train")
            logger.success("データセットの読み込みが完了しました。")
            return dataset
        except Exception:
            logger.exception("データセットの読み込みに失敗しました。パスを確認してください。")
            raise

    def _run_training(self, train_dataset):
        """
        SFTTrainerを使用してモデルのトレーニングを実行します。
        """
        logger.info("MLflowで実験を開始します...")
        mlflow.set_experiment(self.config.get('mlflow_experiment_name', "Default Experiment"))
        mlflow.autolog()

        with mlflow.start_run() as run:
            logger.info(f"MLflow Run ID: {run.info.run_id}")

            training_args_dict = self.config['training_args']
            training_args_dict['seed'] = self.config.get('seed', 42)
            
            trainer = SFTTrainer(
                model=self.model,
                tokenizer=self.tokenizer,
                train_dataset=train_dataset,
                dataset_text_field="text",
                max_seq_length=self.config['max_seq_length'],
                dataset_num_proc=self.config.get('dataset_num_proc', 2),
                packing=self.config.get('packing', False),
                args=TrainingArguments(**training_args_dict),
            )

            if torch.cuda.is_available():
                gpu_stats = torch.cuda.get_device_properties(0)
                max_memory = round(gpu_stats.total_memory / 1024**3, 2)
                logger.info(f"GPU: {gpu_stats.name}, Max Memory: {max_memory} GB")

            logger.info("トレーニングを開始します...")
            trainer_stats = trainer.train()
            logger.success("トレーニングが完了しました。")

            if torch.cuda.is_available():
                used_memory = round(torch.cuda.max_memory_reserved() / 1024**3, 2)
                mlflow.log_metric("peak_gpu_memory_gb", used_memory)
            
            mlflow.log_metric("train_runtime_sec", trainer_stats.metrics['train_runtime'])
            
    def _save_model(self):
        """
        ファインチューニングされたモデルを保存します。
        """
        output_path = self.config['output_model_path']
        logger.info(f"モデルを '{output_path}' に保存しています...")
        self.model.save_pretrained(output_path)
        self.tokenizer.save_pretrained(output_path)
        mlflow.log_artifacts(output_path, artifact_path="model")
        logger.success("モデルの保存が完了しました。")

    def run(self):
        """
        実験の全工程を実行します。
        """
        self._load_model_and_tokenizer()
        self._apply_lora()
        train_dataset = self._load_dataset()
        self._run_training(train_dataset)
        self._save_model()
        logger.info("実験は正常に終了しました。")


class Args(Tap):
    """
    LLMをLoRAでファインチューニングするスクリプトの設定。
    """
    # --- 必須の引数 ---
    input_data_path: str  # 入力となる学習データ（JSONファイル）のパス
    output_model_path: str  # ファインチューニング済みモデルの保存先パス

    # --- モデル設定 ---
    model_name: str = "dx2102/llama-midi"
    max_seq_length: int = 4096
    load_in_4bit: bool = True

    # --- LoRA設定 ---
    lora_r: int = 16
    lora_alpha: int = 16

    # --- トレーニング設定 ---
    per_device_train_batch_size: int = 2
    gradient_accumulation_steps: int = 4
    warmup_steps: int = 5
    num_train_epochs: int = 1
    learning_rate: float = 1e-4
    logging_steps: int = 1
    optim: str = "adamw_8bit"
    weight_decay: float = 0.01
    lr_scheduler_type: str = "linear"
    output_dir: str = "outputs"
    report_to: str = "mlflow"

    # --- 実験管理 ---
    seed: int = 42
    mlflow_experiment_name: str = "MIDI Llama Finetuning Refactored"

    def configure(self):
        # 位置引数を定義
        self.add_argument("input_data_path")
        self.add_argument("output_model_path")


def main():
    """
    スクリプトのエントリーポイント。
    typed-argument-parserを使って引数を解析し、実験クラスをインスタンス化して実行します。
    """
    args = Args(description="LLMをLoRAでファインチューニングするスクリプト").parse_args()

    # ArgsオブジェクトからMidiFinetuningExperimentが期待するconfig辞書を構築
    config = {
        "input_data_path": args.input_data_path,
        "output_model_path": args.output_model_path,
        "model_name": args.model_name,
        "max_seq_length": args.max_seq_length,
        "load_in_4bit": args.load_in_4bit,
        "seed": args.seed,
        "mlflow_experiment_name": args.mlflow_experiment_name,
        
        "lora": {
            "r": args.lora_r,
            "alpha": args.lora_alpha,
            "target_modules": [
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ],
        },

        "training_args": {
            "per_device_train_batch_size": args.per_device_train_batch_size,
            "gradient_accumulation_steps": args.gradient_accumulation_steps,
            "warmup_steps": args.warmup_steps,
            "num_train_epochs": args.num_train_epochs,
            "learning_rate": args.learning_rate,
            "fp16": not torch.cuda.is_bf16_supported(),
            "bf16": torch.cuda.is_bf16_supported(),
            "logging_steps": args.logging_steps,
            "optim": args.optim,
            "weight_decay": args.weight_decay,
            "lr_scheduler_type": args.lr_scheduler_type,
            "output_dir": args.output_dir,
            "report_to": args.report_to,
        },
    }

    experiment = MidiFinetuningExperiment(config)
    experiment.run()


if __name__ == "__main__":
    main()



