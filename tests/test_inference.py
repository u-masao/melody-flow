import json
from unittest.mock import MagicMock, patch

import pytest
from src.model.inference import MidiGenerator


@pytest.fixture
def mock_dependencies():
    """
    MidiGeneratorの依存関係をモック化し、テスト中に注入できるようにします。
    """
    # `inference.py`内でimportされているモジュールをpatchでモック化します
    with patch("src.model.inference.FastLanguageModel") as mock_fast_lm, \
         patch("src.model.inference.transformers") as mock_transformers, \
         patch("src.model.inference.logger") as mock_logger, \
         patch("src.model.inference.NoteTokenizer") as mock_note_tokenizer, \
         patch("src.model.inference.MelodyControlLogitsProcessor") as mock_logits_processor:

        # from_pretrainedが(model, tokenizer)のタプルを返すように設定します
        mock_model = MagicMock()
        mock_tokenizer = MagicMock()
        # テスト中に参照される属性をダミー値で設定します
        mock_tokenizer.eos_token_id = 2
        mock_tokenizer.pad_token_id = 2
        mock_fast_lm.from_pretrained.return_value = (mock_model, mock_tokenizer)

        # pipelineがモックされたパイプラインオブジェクトを返すように設定します
        mock_pipe = MagicMock()
        mock_transformers.pipeline.return_value = mock_pipe

        # モック化したオブジェクトを辞書で返します
        yield {
            "mock_fast_lm": mock_fast_lm,
            "mock_transformers": mock_transformers,
            "mock_logger": mock_logger,
            "mock_note_tokenizer": mock_note_tokenizer,
            "mock_logits_processor": mock_logits_processor,
            "mock_pipe": mock_pipe,
            "mock_tokenizer": mock_tokenizer,
        }


@pytest.fixture
def midi_generator(mock_dependencies):
    """
    モック化された依存関係を持つMidiGeneratorのインスタンスを生成します。
    """
    # この中で `__init__` が呼ばれ、`mock_dependencies`で設定したモックが使われます
    generator = MidiGenerator(model_path="fake/model/path")
    return generator


def test_midi_generator_init(mock_dependencies):
    """
    MidiGeneratorの初期化時に、モデルとパイプラインが正しく設定されるかテストします。
    """
    # Arrange
    model_path = "fake/path"

    # Act
    MidiGenerator(model_path=model_path)

    # Assert
    # FastLanguageModel.from_pretrained が意図した引数で呼ばれたか検証します
    mock_dependencies["mock_fast_lm"].from_pretrained.assert_called_once_with(
        model_name=model_path,
        max_seq_length=4096,
        dtype=None,
        load_in_4bit=True,
    )

    # transformers.pipeline が意図した引数で呼ばれたか検証します
    mock_dependencies["mock_transformers"].pipeline.assert_called_once()
    args, kwargs = mock_dependencies["mock_transformers"].pipeline.call_args
    assert args[0] == "text-generation"
    assert "model" in kwargs
    assert "tokenizer" in kwargs


def test_generate_with_chord_progression(midi_generator, mock_dependencies):
    """
    コード進行が指定された場合に、正しくLogitsProcessorが使用されるかテストします。
    """
    # Arrange
    prompt_dict = {"chord_progression": "Am7 D7 Gmaj7 Cmaj7"}
    prompt_str = json.dumps(prompt_dict)

    # パイプラインの出力を模倣します
    mock_output = [{"generated_text": f"<s>[INST] {prompt_str} [/INST] pitch duration wait velocity instrument\nC4 1.0 0.0 100 piano"}]
    mock_dependencies["mock_pipe"].return_value = mock_output

    # Act
    result = midi_generator.generate(prompt=prompt_str)

    # Assert
    # NoteTokenizerが初期化されたか検証します
    mock_dependencies["mock_note_tokenizer"].assert_called_once_with(mock_dependencies["mock_tokenizer"])

    # MelodyControlLogitsProcessorが適切な引数で初期化されたか検証します
    mock_dependencies["mock_logits_processor"].assert_called_once()
    _, kwargs = mock_dependencies["mock_logits_processor"].call_args
    assert kwargs["chord_progression"] == prompt_dict["chord_progression"]
    assert "note_tokenizer" in kwargs

    # pipelineがLogitsProcessor付きで呼ばれたか検証します
    _, pipe_kwargs = mock_dependencies["mock_pipe"].call_args
    assert "logits_processor" in pipe_kwargs
    assert len(pipe_kwargs["logits_processor"]) == 1

    # 結果が正しくパースされたか検証します
    assert result == "pitch duration wait velocity instrument\nC4 1.0 0.0 100 piano"


def test_generate_without_chord_progression(midi_generator, mock_dependencies):
    """
    コード進行が指定されない場合に、LogitsProcessorが使用されないことをテストします。
    """
    # Arrange
    prompt_dict = {"title": "some title"}
    prompt_str = json.dumps(prompt_dict)

    mock_output = [{"generated_text": f"<s>[INST] {prompt_str} [/INST] pitch duration wait velocity instrument\nD4 0.5 0.0 100 guitar"}]
    mock_dependencies["mock_pipe"].return_value = mock_output

    # Act
    result = midi_generator.generate(prompt=prompt_str)

    # Assert
    # LogitsProcessorが初期化されていないことを確認します
    mock_dependencies["mock_logits_processor"].assert_not_called()

    # pipelineのlogits_processorが空のリストであることを確認します
    _, pipe_kwargs = mock_dependencies["mock_pipe"].call_args
    assert "logits_processor" in pipe_kwargs
    assert len(pipe_kwargs["logits_processor"]) == 0

    # 結果が正しくパースされたか検証します
    assert result == "pitch duration wait velocity instrument\nD4 0.5 0.0 100 guitar"


def test_generate_with_invalid_json_prompt(midi_generator, mock_dependencies):
    """
    不正なJSON形式のプロンプトが与えられた場合に、警告ログが出て、制約なしで実行されることをテストします。
    """
    # Arrange
    prompt_str = "this is not a json"

    mock_output = [{"generated_text": f"<s>[INST] {prompt_str} [/INST] pitch duration wait velocity instrument\nE4 0.2 0.0 100 violin"}]
    mock_dependencies["mock_pipe"].return_value = mock_output

    # Act
    result = midi_generator.generate(prompt=prompt_str)

    # Assert
    # 警告ログが意図通りに呼ばれたか検証します
    mock_dependencies["mock_logger"].warning.assert_called_once_with(
        "プロンプトからコード進行を抽出できませんでした。制約なしで生成します。"
    )

    # LogitsProcessorが初期化されていないことを確認します
    mock_dependencies["mock_logits_processor"].assert_not_called()

    # pipelineのlogits_processorが空のリストであることを確認します
    _, pipe_kwargs = mock_dependencies["mock_pipe"].call_args
    assert len(pipe_kwargs["logits_processor"]) == 0

    # 結果が正しくパースされたか検証します
    assert result == "pitch duration wait velocity instrument\nE4 0.2 0.0 100 violin"


def test_generate_output_parsing(midi_generator, mock_dependencies):
    """
    パイプラインからの出力が正しくパースされ、プロンプト部分が除去されるかをテストします。
    """
    # Arrange
    prompt_str = '{"title": "test"}'
    generated_part = "pitch duration wait velocity instrument\nG4 1.0 0.0 100 piano"
    # [/INST] タグが複数含まれるようなエッジケースも想定します
    pipeline_output_text = f"<s>[INST] {prompt_str} [/INST] some other text [/INST] {generated_part}"
    mock_output = [{"generated_text": pipeline_output_text}]
    mock_dependencies["mock_pipe"].return_value = mock_output

    # Act
    result = midi_generator.generate(prompt=prompt_str)

    # Assert
    # 最後の[/INST]以降の部分だけが正しく抽出されているか検証します
    assert result == generated_part.strip()
