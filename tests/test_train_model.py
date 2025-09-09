import pytest
from unittest.mock import patch

from src.model.train_model import Args, create_config_from_args

def test_args_parsing():
    """
    Argsクラスがコマンドライン引数のリストを正しくパースすることをテストします。
    """
    test_argv = [
        "script_name",
        "data/my_data.json",
        "models/my_model",
        "--model_name", "test/model",
        "--num_train_epochs", "3",
        "--learning_rate", "1e-5",
    ]

    # patchを使用してコマンドライン引数をシミュレートします
    with patch("sys.argv", test_argv):
        args = Args().parse_args()

    assert args.input_data_path == "data/my_data.json"
    assert args.output_model_path == "models/my_model"
    assert args.model_name == "test/model"
    assert args.num_train_epochs == 3
    assert args.learning_rate == 1e-5
    # デフォルト値を確認します
    assert args.lora_r == 16

def test_create_config_from_args():
    """
    Argsオブジェクトから設定辞書が正しく作成されることをテストします。
    """
    # ダミーのArgsオブジェクトを作成します
    args = Args().parse_args([
        "data/dummy.json",
        "models/dummy_output",
        "--lora_r", "32",
        "--learning_rate", "5e-5"
    ])

    config = create_config_from_args(args)

    # トップレベルのキーを確認します
    assert config["input_data_path"] == "data/dummy.json"
    assert config["output_model_path"] == "models/dummy_output"

    # ネストされたLoRA設定を確認します
    assert isinstance(config["lora"], dict)
    assert config["lora"]["r"] == 32
    assert "target_modules" in config["lora"]

    # ネストされたtraining_args設定を確認します
    assert isinstance(config["training_args"], dict)
    assert config["training_args"]["learning_rate"] == 5e-5
    assert config["training_args"]["report_to"] == "mlflow" # デフォルト値を確認
    assert "fp16" in config["training_args"] # 動的に設定された値を確認
