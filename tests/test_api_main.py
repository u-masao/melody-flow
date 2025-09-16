import base64
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# テスト対象のFastAPIアプリケーションと依存関係をインポート
from src.api.main import app, get_model_dependencies, ModelDependencies


# --- テスト用のモックとフィクスチャ ---

@pytest.fixture
def mock_model_deps():
    """`get_model_dependencies`をオーバーライドするためのモック依存関係"""
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_note_helper = MagicMock()

    # model.generateが返すトークンIDのリスト（ダミー）
    # 実際の出力に近い形式のダミーテキストを返す
    mock_model.generate.return_value = [1, 2, 3]

    # tokenizer.decodeの戻り値を設定
    # これが`generate_midi_from_model`の返り値になり、`parse_and_encode_midi`に渡される
    dummy_decoded_output = "pitch duration wait velocity instrument\n60 500 0 100 0"
    mock_tokenizer.decode.return_value = dummy_decoded_output

    return ModelDependencies(model=mock_model, tokenizer=mock_tokenizer, note_helper=mock_note_helper)


@pytest.fixture
def client(mock_model_deps):
    """
    依存関係をモックに差し替えたテストクライアントを提供するフィクスチャ
    """
    # get_model_dependenciesが常にmock_model_depsを返すようにオーバーライド
    app.dependency_overrides[get_model_dependencies] = lambda: mock_model_deps

    # TestClientを生成
    with TestClient(app) as test_client:
        yield test_client

    # テスト終了後にオーバーライドをクリア
    app.dependency_overrides.clear()


# --- テストケース ---

def test_generate_melody_success(client, mock_model_deps):
    """/generateエンドポイントが正常に動作するかテスト"""
    # Arrange
    chord_progression = "C-G"
    style = "jazz"
    variation = 42

    # Act
    response = client.get(
        f"/generate?chord_progression={chord_progression}&style={style}&variation={variation}"
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "chord_melodies" in data

    # 2つのコードが処理されたか
    assert "C" in data["chord_melodies"]
    assert "G" in data["chord_melodies"]

    # Base64エンコードされたデータが正しいか
    # `parse_and_encode_midi`はヘッダーを除いた部分をエンコードする
    expected_note_data = "60 500 0 100 0"
    expected_b64 = base64.b64encode(expected_note_data.encode()).decode()
    assert data["chord_melodies"]["C"] == expected_b64

    # model.generateが正しい回数呼ばれたか (コードの数だけ)
    assert mock_model_deps.model.generate.call_count == 2


def test_generate_melody_duplicate_chords(client):
    """重複するコード名が正しく処理されるかテスト (e.g., C, C_2)"""
    # Arrange
    chord_progression = "C-C"

    # Act
    response = client.get(
        f"/generate?chord_progression={chord_progression}&style=pop&variation=1"
    )

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert "C" in data["chord_melodies"]
    assert "C_2" in data["chord_melodies"]


def test_generate_melody_missing_params(client):
    """必須パラメータが欠けている場合に422エラーが返るかテスト"""
    # chord_progressionがない
    response = client.get("/generate?style=rock")
    assert response.status_code == 422  # Unprocessable Entity

    # styleがない
    response = client.get("/generate?chord_progression=Am-G")
    assert response.status_code == 422


def test_read_index(client):
    """ルートURL ("/") がindex.htmlを返すかテスト"""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    # より確実な、ファイル内に存在する文字列でアサートする
    assert '<span class="text-xl font-bold">Melody Flow</span>' in response.text
