import sys
from unittest.mock import MagicMock, patch

import pytest
import unsloth  # noqa: F401


@pytest.fixture
def mock_transformers():
    """transformersライブラリのモデル読み込みをモックするフィクスチャ"""
    with (
        patch("src.model.utils.AutoModelForCausalLM.from_pretrained") as mock_lm,
        patch("src.model.utils.AutoTokenizer.from_pretrained") as mock_tok,
    ):
        mock_lm.return_value.to.return_value = MagicMock()
        mock_tok.return_value = MagicMock()
        yield mock_lm, mock_tok


@pytest.fixture
def mock_unsloth():
    """unslothライブラリのモデル読み込みをモックするフィクスチャ"""
    with patch("src.model.utils.FastLanguageModel.from_pretrained") as mock_fast:
        mock_fast.return_value = (MagicMock(), MagicMock())
        yield mock_fast


def test_load_model_and_tokenizer_local_path(mock_unsloth, monkeypatch):
    """ローカルパスが指定された場合にUnslothが使用されることをテストする"""
    monkeypatch.setattr("os.path.isdir", lambda path: True)
    from src.model import utils

    utils.load_model_and_tokenizer("./models/llama-midi.pth/")
    mock_unsloth.assert_called_once_with(
        model_name="./models/llama-midi.pth/", max_seq_length=4096, dtype=None, load_in_4bit=True
    )


def test_load_model_and_tokenizer_hub_path(mock_transformers, monkeypatch):
    """Hugging Face Hubのパスが指定された場合にtransformersが使用されることをテストする"""
    monkeypatch.setattr("os.path.isdir", lambda path: False)
    from src.model import utils

    utils.load_model_and_tokenizer("dx2102/llama-midi", disable_unsloth=True)
    mock_transformers[0].assert_called_once()
    mock_transformers[1].assert_called_once_with("dx2102/llama-midi")


def test_load_model_and_tokenizer_load_error(mock_unsloth, monkeypatch):
    """モデル読み込み中に例外が発生した場合にNoneが返されることをテストする"""
    monkeypatch.setattr("os.path.isdir", lambda path: True)
    mock_unsloth.side_effect = Exception("Test error")
    from src.model import utils

    result = utils.load_model_and_tokenizer("any/path")
    assert result == (None, None, None, None)


# 失敗していたテストを、より安定した方法に修正
def test_get_op_decorator_switches_by_env(monkeypatch):
    """_get_op_decoratorが環境変数に応じて正しい関数を返すかテストする"""
    from src.model.utils import _get_op_decorator

    # --- 開発モードのテスト ---
    monkeypatch.setenv("APP_ENV", "development")
    mock_weave = MagicMock()
    # sys.modulesにモックを挿入して、`import weave`が成功するようにする
    monkeypatch.setitem(sys.modules, "weave", mock_weave)

    dev_op = _get_op_decorator()
    assert dev_op is mock_weave.op

    # --- 本番モードのテスト ---
    monkeypatch.setenv("APP_ENV", "production")
    prod_op = _get_op_decorator()
    # 返されたものがモックではなく、'dummy_op'という名前の関数であることを確認
    assert prod_op is not mock_weave.op
    assert prod_op.__name__ == "dummy_op"
