import pytest
from unittest.mock import patch, MagicMock, ANY
from src.model.train_model import main, MidiFinetuningExperiment, Args


@pytest.fixture
def sample_config():
    """MidiFinetuningExperimentに渡すためのサンプル設定辞書を提供するフィクスチャ"""
    return {
        "input_data_path": "/fake/data.json",
        "output_model_path": "/fake/model",
        "model_name": "fake/model_name",
        "max_seq_length": 1024,
        "load_in_4bit": True,
        "seed": 42,
        "mlflow_experiment_name": "Test Experiment",
        "lora": {
            "r": 8,
            "alpha": 8,
            "target_modules": ["q_proj", "v_proj"],
        },
        "training_args": {
            "per_device_train_batch_size": 1,
            "gradient_accumulation_steps": 1,
            "warmup_steps": 1,
            "num_train_epochs": 1,
            "learning_rate": 1e-5,
            "fp16": False,
            "bf16": True,
            "logging_steps": 1,
            "optim": "adamw_8bit",
            "weight_decay": 0.01,
            "lr_scheduler_type": "linear",
            "output_dir": "outputs_test",
            "report_to": "mlflow",
        },
    }


@patch("src.model.train_model.Args")
@patch("src.model.train_model.MidiFinetuningExperiment")
def test_main_flow(mock_experiment_class, mock_args_class):
    """main関数が引数を正しくパースし、実験クラスを初期化・実行するかテスト"""
    # Arrange: 引数パーサーのモックを設定
    mock_args = MagicMock()
    mock_args.input_data_path = "/fake/data.json"
    mock_args.output_model_path = "/fake/model"
    # 他の引数も同様に設定...
    mock_args.lora_r = 8
    mock_args.lora_alpha = 8
    mock_args_class.return_value.parse_args.return_value = mock_args

    # Act
    main()

    # Assert
    # MidiFinetuningExperimentが適切なconfigで初期化されたか
    mock_experiment_class.assert_called_once()
    config_arg = mock_experiment_class.call_args[0][0]
    assert config_arg["input_data_path"] == "/fake/data.json"
    assert config_arg["lora"]["r"] == 8

    # experiment.run()が呼ばれたか
    mock_experiment_instance = mock_experiment_class.return_value
    mock_experiment_instance.run.assert_called_once()


# 複数のパッチャーをまとめる
@patch("src.model.train_model.FastLanguageModel")
@patch("src.model.train_model.load_dataset")
@patch("src.model.train_model.SFTTrainer")
@patch("src.model.train_model.TrainingArguments")
@patch("src.model.train_model.mlflow")
class TestMidiFinetuningExperiment:
    def test_run_method_calls_steps_in_order(
        self, mock_mlflow, mock_train_args, mock_trainer, mock_load_ds, mock_fast_lm, sample_config
    ):
        """run()メソッドが各ステップを正しい順序で呼び出すかテスト"""
        experiment = MidiFinetuningExperiment(sample_config)

        # 各ステップのメソッドをモック化
        experiment._load_model_and_tokenizer = MagicMock()
        experiment._apply_lora = MagicMock()
        experiment._load_dataset = MagicMock()
        experiment._run_training = MagicMock()
        experiment._save_model = MagicMock()

        # Act
        experiment.run()

        # Assert
        calls = [
            'experiment._load_model_and_tokenizer()',
            'experiment._apply_lora()',
            'experiment._load_dataset()',
            'experiment._run_training(ANY)',
            'experiment._save_model()',
        ]
        # ANYを使って呼び出しを表現
        experiment._load_model_and_tokenizer.assert_called_once()
        experiment._apply_lora.assert_called_once()
        experiment._load_dataset.assert_called_once()
        experiment._run_training.assert_called_once()
        experiment._save_model.assert_called_once()

    def test_load_model_and_tokenizer(self, mock_mlflow, mock_train_args, mock_trainer, mock_load_ds, mock_fast_lm, sample_config):
        """モデルとトークナイザーが正しくロードされるかテスト"""
        # Arrange: from_pretrainedが(model, tokenizer)のタプルを返すように設定
        mock_fast_lm.from_pretrained.return_value = (MagicMock(), MagicMock())

        # Act
        experiment = MidiFinetuningExperiment(sample_config)
        experiment._load_model_and_tokenizer()

        # Assert
        mock_fast_lm.from_pretrained.assert_called_once_with(
            model_name=sample_config["model_name"],
            max_seq_length=sample_config["max_seq_length"],
            dtype=ANY,
            load_in_4bit=sample_config["load_in_4bit"],
        )
        assert experiment.model is not None
        assert experiment.tokenizer is not None

    def test_apply_lora(self, mock_mlflow, mock_train_args, mock_trainer, mock_load_ds, mock_fast_lm, sample_config):
        """LoRAが正しく適用されるかテスト"""
        experiment = MidiFinetuningExperiment(sample_config)
        mock_model_instance = MagicMock()
        experiment.model = mock_model_instance  # 事前にモデルがロードされていると仮定

        # Act
        experiment._apply_lora()

        # Assert: 呼び出しをより堅牢に検証
        mock_fast_lm.get_peft_model.assert_called_once()
        call_args, call_kwargs = mock_fast_lm.get_peft_model.call_args

        assert call_args[0] == mock_model_instance
        assert call_kwargs['r'] == sample_config['lora']['r']
        assert call_kwargs['lora_alpha'] == sample_config['lora']['alpha']
        assert call_kwargs['target_modules'] == sample_config['lora']['target_modules']
        assert call_kwargs['random_state'] == sample_config['seed']

    def test_run_training(self, mock_mlflow, mock_train_args, mock_trainer, mock_load_ds, mock_fast_lm, sample_config):
        """トレーニングのセットアップと実行が正しく行われるかテスト"""
        experiment = MidiFinetuningExperiment(sample_config)
        experiment.model = MagicMock()
        experiment.tokenizer = MagicMock()
        mock_dataset = MagicMock()

        # Act
        experiment._run_training(mock_dataset)

        # Assert
        mock_mlflow.set_experiment.assert_called_once_with(sample_config["mlflow_experiment_name"])
        mock_mlflow.start_run.assert_called_once()

        # TrainingArgumentsが正しい設定で初期化されるか
        mock_train_args.assert_called_once()
        actual_args = mock_train_args.call_args[1] # kwargs
        assert actual_args['output_dir'] == sample_config['training_args']['output_dir']
        assert actual_args['seed'] == sample_config['seed']

        # SFTTrainerが正しい設定で初期化されるか
        mock_trainer.assert_called_once_with(
            model=experiment.model,
            tokenizer=experiment.tokenizer,
            train_dataset=mock_dataset,
            dataset_text_field="text",
            max_seq_length=sample_config["max_seq_length"],
            dataset_num_proc=ANY,
            packing=ANY,
            args=mock_train_args.return_value,
        )

        # trainer.train()が呼ばれるか
        mock_trainer.return_value.train.assert_called_once()

    def test_save_model(self, mock_mlflow, mock_train_args, mock_trainer, mock_load_ds, mock_fast_lm, sample_config):
        """モデルの保存が正しく行われるかテスト"""
        experiment = MidiFinetuningExperiment(sample_config)
        experiment.model = MagicMock()
        experiment.tokenizer = MagicMock()

        # Act
        experiment._save_model()

        # Assert
        output_path = sample_config["output_model_path"]
        experiment.model.save_pretrained.assert_called_once_with(output_path)
        experiment.tokenizer.save_pretrained.assert_called_once_with(output_path)
        mock_mlflow.log_artifacts.assert_called_once_with(output_path, artifact_path="model")
