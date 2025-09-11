#!/bin/bash

# APIのエンドポイントURL
# docker-compose.yamlでNginxがホストの80/443ポートにマッピングされていることを前提とする
API_URL="http://localhost/generate"
# HTTPSにリダイレクトされることを想定し、-Lオプションを有効にする
# テスト環境の自己署名証明書を許容するために-kも追加
CURL_OPTS="-s -L -k -o /dev/null -w %{http_code}"

# 事前生成されたクエリデータが格納されているディレクトリ
DATA_DIR="data/pregenerated"

# カウンター初期化
SUCCESS_COUNT=0
FAILURE_COUNT=0

# データディレクトリ内のすべてのJSONファイルに対してループ
for file in $(find ${DATA_DIR} -type f -name "*.json" | sort); do
    echo "Sending request with ${file}..."

    # curlコマンドでPOSTリクエストを送信
    HTTP_CODE=$(curl ${CURL_OPTS} -X POST "${API_URL}" \
        -H "Content-Type: application/json" \
        -d @"${file}")

    # レスポンスコードをチェック
    if [ "${HTTP_CODE}" -eq 200 ]; then
        echo "  -> SUCCESS (HTTP 200)"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo "  -> FAILURE (HTTP ${HTTP_CODE})"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
    fi

    # サーバーに過度な負荷をかけないよう、少し待機
    sleep 0.1
done

echo "----------------------------------------"
echo "Warmup Complete."
echo "  Successful requests: ${SUCCESS_COUNT}"
echo "  Failed requests:     ${FAILURE_COUNT}"
echo "----------------------------------------"

# 失敗したリクエストがあれば、ゼロ以外のステータスコードで終了
if [ ${FAILURE_COUNT} -gt 0 ]; then
    exit 1
fi
