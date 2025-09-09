from fastapi.testclient import TestClient
import pytest
from unittest.mock import MagicMock, patch

# アプリをインポートする前にサービスをモックします
# これにより、アプリがモックインスタンスで作成されることが保証されます
mock_melody_service = MagicMock()
mock_model_manager = MagicMock()

# patchを使用してサービスモジュール内のインスタンスを置き換えます
patch_model_manager = patch('src.api.main.model_manager', mock_model_manager)
patch_melody_service = patch('src.api.main.melody_service', mock_melody_service)

# パッチを開始
patch_model_manager.start()
patch_melody_service.start()

# これでアプリをインポートできます
from src.api.main import app

# 他のテストに干渉しないように、アプリのロード後にパッチを停止します
patch_model_manager.stop()
patch_melody_service.stop()


@pytest.fixture
def client():
    """FastAPIアプリ用のTestClientインスタンスを作成します。"""
    with TestClient(app) as c:
        yield c

def test_read_index(client: TestClient):
    """ルートエンドポイントが静的なindex.htmlを提供することを確認するテスト。"""
    # テストで実際のファイルシステム設定なしにFileResponseの内容を簡単にテストすることはできませんが、
    # エンドポイントが存在し、成功ステータスを返すことは確認できます。
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')

def test_generate_melody_success(client: TestClient):
    """成功レスポンスの場合の/generateエンドポイントをテストします。"""
    # 成功レスポンスを返すようにモックサービスを設定します
    mock_melodies = {"C": "encoded_midi_data_1"}
    mock_raw = {"C": "raw_output_1"}
    mock_melody_service.generate_melodies_for_chords.return_value = (mock_melodies, mock_raw)
    mock_model_manager.is_ready.return_value = True

    # リクエストを実行します
    request_data = {"chord_progression": "C", "style": "pop"}
    response = client.post("/generate", json=request_data)

    # アサーション
    assert response.status_code == 200
    response_json = response.json()
    assert response_json["chord_melodies"] == mock_melodies
    assert response_json["raw_outputs"] == mock_raw
    mock_melody_service.generate_melodies_for_chords.assert_called_once_with(
        chord_progression="C", style="pop"
    )

def test_generate_melody_when_model_not_ready(client: TestClient):
    """モデルの準備ができていない場合の/generateエンドポイントをテストします。"""
    # 準備ができていないようにモックモデルマネージャーを設定します
    mock_model_manager.is_ready.return_value = False

    request_data = {"chord_progression": "C", "style": "pop"}
    response = client.post("/generate", json=request_data)

    assert response.status_code == 503
    assert response.json() == {"detail": "モデルがロードされていないか、準備ができていません。"}

def test_generate_melody_internal_error(client: TestClient):
    """サービスが例外を発生させた場合の/generateエンドポイントをテストします。"""
    # 例外を発生させるようにモックサービスを設定します
    mock_model_manager.is_ready.return_value = True
    mock_melody_service.generate_melodies_for_chords.side_effect = ValueError("何かがうまくいかなかった")

    request_data = {"chord_progression": "C", "style": "pop"}
    response = client.post("/generate", json=request_data)

    assert response.status_code == 500
    assert "内部エラーが発生しました: 何かがうまくいかなかった" in response.json()["detail"]

# テスト終了後にモックをリセットします
@pytest.fixture(autouse=True)
def reset_mocks():
    """各テストの前にモックをリセットします。"""
    mock_melody_service.reset_mock()
    mock_model_manager.reset_mock()
