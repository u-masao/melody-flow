import pytest
from unittest.mock import patch, MagicMock

from src.model.inference import MidiGenerator, InferenceArgs

# --- モック ---

@pytest.fixture
def mock_model_loading():
    """モデル読み込み関数をモックするためのフィクスチャ。"""
    with patch("src.model.inference.FastLanguageModel.from_pretrained") as mock_load, \
         patch("src.model.inference.NoteTokenizer") as mock_note_tok, \
         patch("src.model.inference.transformers.pipeline") as mock_pipeline:

        # 戻り値をモックします
        mock_model = MagicMock()
        mock_tokenizer = MagicMock()
        mock_load.return_value = (mock_model, mock_tokenizer)

        mock_pipe_instance = MagicMock()
        mock_pipeline.return_value = mock_pipe_instance

        yield mock_load, mock_note_tok, mock_pipeline, mock_pipe_instance

# --- テスト ---

class TestMidiGenerator:

    def test_initialization(self, mock_model_loading):
        """MidiGeneratorが依存関係を呼び出して正しく初期化されることをテストします。"""
        mock_load, mock_note_tok, mock_pipeline, _ = mock_model_loading

        generator = MidiGenerator(model_path="fake/path")

        mock_load.assert_called_once_with(
            model_name="fake/path",
            max_seq_length=4096,
            dtype=None,
            load_in_4bit=True
        )
        mock_note_tok.assert_called_once()
        mock_pipeline.assert_called_once()
        assert generator.pipe is not None

    def test_parse_prompt(self, mock_model_loading):
        """内部プロンプト解析ロジックをテストします。"""
        generator = MidiGenerator(model_path="fake/path")

        # 有効なJSON
        style, progression = generator._parse_prompt(
            '{"style": "jazz", "chord_progression": "C-G-Am-F"}'
        )
        assert style == "jazz"
        assert progression == "C-G-Am-F"

        # 不正な形式のJSON
        style, progression = generator._parse_prompt('{"style": "pop", ')
        assert style is None
        assert progression is None

        # JSONではない
        style, progression = generator._parse_prompt("ただの文字列")
        assert style is None
        assert progression is None

    def test_generate_logic_with_progression(self, mock_model_loading):
        """コード進行が提供された場合のgenerateメソッドのロジックをテストします。"""
        _, _, _, mock_pipe_instance = mock_model_loading

        # パイプライン呼び出しのモック戻り値を設定します
        mock_pipe_instance.return_value = [{
            "generated_text": "<s>[INST] style=pop, chord_progression=C-G [/INST] 60 1 1 1"
        }]

        generator = MidiGenerator(model_path="fake/path")
        prompt = '{"style": "pop", "chord_progression": "C-G"}'

        result = generator.generate(prompt=prompt, max_new_tokens=10)

        # 結果を確認します
        assert result == "60 1 1 1"

        # パイプラインが正しく呼び出されたことを確認します
        call_args, call_kwargs = mock_pipe_instance.call_args

        # フォーマットされたプロンプトを確認します
        expected_prompt = "<s>[INST] style=pop, chord_progression=C-G [/INST] pitch duration wait velocity instrument\n"
        assert call_args[0] == expected_prompt

        # logits_processorが作成されて渡されたことを確認します
        assert "logits_processor" in call_kwargs
        assert len(call_kwargs["logits_processor"]) == 1
        assert "max_new_tokens" in call_kwargs and call_kwargs["max_new_tokens"] == 10

    def test_generate_logic_no_progression(self, mock_model_loading):
        """コード進行がない場合のgenerateメソッドのロジックをテストします。"""
        _, _, _, mock_pipe_instance = mock_model_loading
        mock_pipe_instance.return_value = [{"generated_text": "[/INST] some text"}]

        generator = MidiGenerator(model_path="fake/path")
        prompt = '簡単なテキストプロンプト'

        generator.generate(prompt=prompt)

        _, call_kwargs = mock_pipe_instance.call_args

        # 進行がない場合にlogits_processorが渡されないことを確認します
        assert "logits_processor" in call_kwargs
        assert len(call_kwargs["logits_processor"]) == 0
