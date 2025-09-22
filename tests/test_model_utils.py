from unittest.mock import MagicMock, patch

import pytest
import torch


@patch("src.model.utils.FastLanguageModel.from_pretrained")
def test_load_model_and_tokenizer_local_unsloth_success(mock_from_pretrained):
    """
    ローカルパスからUnslothモデルが正常に読み込まれることをテストする
    """
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_from_pretrained.return_value = (mock_model, mock_tokenizer)

    from src.model import utils

    model, tokenizer, note_helper, device = utils.load_model_and_tokenizer(
        model_path="local/path", disable_unsloth=False
    )

    mock_from_pretrained.assert_called_once()
    assert model is mock_model
    assert tokenizer is mock_tokenizer
    assert note_helper is not None
    assert device is not None


@patch("src.model.utils.AutoTokenizer.from_pretrained")
@patch("src.model.utils.AutoModelForCausalLM.from_pretrained")
def test_load_model_and_tokenizer_hub_success(mock_model_loader, mock_tokenizer_loader):
    """
    Hugging Face Hubからモデルが正常に読み込まれることをテストする
    """
    mock_model_to_device = MagicMock()
    mock_model_instance = MagicMock()
    mock_model_loader.return_value = mock_model_instance
    mock_model_instance.to.return_value = mock_model_to_device

    mock_tokenizer = MagicMock()
    mock_tokenizer_loader.return_value = mock_tokenizer

    from src.model import utils

    model, tokenizer, note_helper, device = utils.load_model_and_tokenizer(
        model_path="hf/some-model", disable_unsloth=True
    )

    mock_model_loader.assert_called_once_with("hf/some-model", torch_dtype=torch.bfloat16)
    mock_tokenizer_loader.assert_called_once_with("hf/some-model")
    assert model is mock_model_to_device
    assert tokenizer is mock_tokenizer


@patch("src.model.utils.FastLanguageModel.from_pretrained")
def test_load_model_and_tokenizer_load_error(mock_from_pretrained):
    """
    モデル読み込み中に例外が発生した場合に、その例外が再送出されることをテストする
    """
    # from_pretrainedが例外を投げるように設定
    mock_from_pretrained.side_effect = Exception("Test error")

    from src.model import utils

    # 例外がraiseされることを確認
    with pytest.raises(Exception, match="Test error"):
        utils.load_model_and_tokenizer(model_path="any/path", disable_unsloth=False)

    # モックが呼び出されたことを確認
    mock_from_pretrained.assert_called_once()


def test_generate_midi_from_model():
    """
    generate_midi_from_modelが正しく呼び出されることをテストする
    """
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_processor = MagicMock()

    # tokenizer() の戻り値が .to() メソッドを持つようにする
    mock_inputs = MagicMock()
    mock_inputs.to.return_value = mock_inputs
    mock_tokenizer.return_value = mock_inputs

    mock_tokenizer.eos_token_id = 0
    mock_tokenizer.decode.return_value = "decoded_output"
    mock_model.generate.return_value = torch.tensor([[1, 2, 3, 4, 5]])

    from src.model import utils

    result = utils.generate_midi_from_model(
        model=mock_model,
        tokenizer=mock_tokenizer,
        device="cpu",
        prompt="test prompt",
        processor=mock_processor,
        seed=42,
    )

    assert result == "decoded_output"
    mock_tokenizer.assert_called_once_with("test prompt", return_tensors="pt")
    mock_inputs.to.assert_called_once_with("cpu")
    mock_model.generate.assert_called_once()
    generate_kwargs = mock_model.generate.call_args.kwargs
    assert "logits_processor" in generate_kwargs
