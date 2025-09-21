import sys

from datasets import load_dataset
from loguru import logger

# 共通のモデル読み込み関数をインポート
from src.model.utils import load_model_and_tokenizer
from tap import Tap
import torch
from transformers import TrainingArguments
from trl import SFTTrainer
from unsloth import FastLanguageModel
import wandb


class MidiFinetuningExperiment:
    """
    MIDI生成モデルのファインチューニング実験を管理するクラス。
    """

    def __init__(self, config: dict):
        """
        実験の設定を初期化します。
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
        共通関数を使用して、事前学習済みモデルとトークナイザーを読み込みます。
        """
        # utils.pyの共通関数を呼び出す
        model, tokenizer, _, _ = load_model_and_tokenizer(self.config["model_name"])
        if model is None or tokenizer is None:
            raise RuntimeError("モデルの読み込みに失敗しました。")
        self.model = model
        self.tokenizer = tokenizer

    def _apply_lora(self):
        """
        モデルにLoRAを適用します。
        """
        logger.info("モデルにLoRAアダプターを適用しています...")
        lora_config = self.config["lora"]
        self.model = FastLanguageModel.get_peft_model(
            self.model,
            r=lora_config["r"],
            target_modules=lora_config["target_modules"],
            lora_alpha=lora_config["alpha"],
            lora_dropout=lora_config.get("dropout", 0),
            bias="none",
            use_gradient_checkpointing=True,
            random_state=self.config.get("seed", 42),
        )
        logger.success("LoRAの適用が完了しました。")

    def _load_dataset(self):
        """
        学習用データセットを読み込みます。
        """
        logger.info(f"データセットを '{self.config['input_data_path']}' から読み込んでいます...")
        try:
            dataset = load_dataset(
                "json", data_files=self.config["input_data_path"], split="train"
            )
            logger.success("データセットの読み込みが完了しました。")
            return dataset
        except Exception:
            logger.exception("データセットの読み込みに失敗しました。パスを確認してください。")
            raise

    def _run_training(self, train_dataset, run):
        """
        SFTTrainerを使用してモデルのトレーニングを実行します。
        """
        try:
            dataset_artifact = run.use_artifact(
                f"{self.config['dataset_artifact_name']}:latest", type="dataset"
            )
            logger.info(f"Using dataset artifact: {dataset_artifact.name}")
        except wandb.errors.CommError as e:
            logger.error(f"Failed to use artifact. Does it exist in the project? Error: {e}")
            logger.error("Please run the `make_dataset` stage first to create the artifact.")
            sys.exit(1)

        training_args_dict = self.config["training_args"]
        training_args_dict["seed"] = self.config.get("seed", 42)
        training_args_dict["report_to"] = "wandb"

        trainer = SFTTrainer(
            model=self.model,
            tokenizer=self.tokenizer,
            train_dataset=train_dataset,
            dataset_text_field="text",
            max_seq_length=self.config["max_seq_length"],
            dataset_num_proc=self.config.get("dataset_num_proc", 2),
            packing=self.config.get("packing", False),
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
            wandb.log({"peak_gpu_memory_gb": used_memory})

        wandb.log({"train_runtime_sec": trainer_stats.metrics["train_runtime"]})

    def _save_model(self, run):
        """
        ファインチューニングされたモデルを保存し、WandB Artifactとして登録します。
        """
        output_path = self.config["output_model_path"]
        logger.info(f"モデルを '{output_path}' に保存しています...")
        self.model.save_pretrained(output_path)
        self.tokenizer.save_pretrained(output_path)
        logger.success("モデルの保存が完了しました。")

        logger.info("モデルをWandB Artifactとして登録しています...")
        model_artifact = wandb.Artifact(
            self.config["output_model_artifact_name"],
            type="model",
            description=f"Fine-tuned model based on {self.config['model_name']}.",
            metadata=self.config,
        )
        model_artifact.add_dir(output_path)
        run.log_artifact(model_artifact)
        logger.success("WandB Artifactの登録が完了しました。")

    def run(self):
        """
        実験の全工程を実行します。
        """
        run = wandb.init(
            project=self.config.get("wandb_project", "melody-flow"),
            config=self.config,
            job_type="train",
        )
        logger.info(f"WandB Run ID: {run.id}")

        try:
            self._load_model_and_tokenizer()
            self._apply_lora()
            train_dataset = self._load_dataset()
            self._run_training(train_dataset, run)
            self._save_model(run)
            logger.info("実験は正常に終了しました。")
        finally:
            if run:
                run.finish()


class Args(Tap):
    """
    LLMをLoRAでファインチューニングするスクリプトの設定。
    """

    input_data_path: str
    output_model_path: str
    model_name: str = "dx2102/llama-midi"
    max_seq_length: int = 4096
    load_in_4bit: bool = True
    lora_r: int = 16
    lora_alpha: int = 16
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
    seed: int = 42

    # --- WandB設定 ---
    wandb_project: str = "melody-flow-model-manage"
    dataset_artifact_name: str = "wjazzd-sft-dataset"
    output_model_artifact_name: str = "llama-midi-finetuned"

    def configure(self):
        self.add_argument("input_data_path")
        self.add_argument("output_model_path")


def main():
    args = Args(description="LLMをLoRAでファインチューニングするスクリプト").parse_args()

    config = {
        "input_data_path": args.input_data_path,
        "output_model_path": args.output_model_path,
        "model_name": args.model_name,
        "max_seq_length": args.max_seq_length,
        "load_in_4bit": args.load_in_4bit,
        "seed": args.seed,
        "wandb_project": args.wandb_project,
        "dataset_artifact_name": args.dataset_artifact_name,
        "output_model_artifact_name": args.output_model_artifact_name,
        "lora": {
            "r": args.lora_r,
            "alpha": args.lora_alpha,
            "target_modules": [
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
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
            "report_to": "wandb",
        },
    }

    experiment = MidiFinetuningExperiment(config)
    experiment.run()


if __name__ == "__main__":
    main()
