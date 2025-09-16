# ==============================================================================
# 変数
# ==============================================================================

AWS_PROFILE_NAME := melody-flow
S3_BUCKET_NAME := melody-flow.click
DOCKER_IMAGE_PROD := "melody-flow-generator:prod"
DOCKER_IMAGE_DEV := "melody-flow-generator:dev"
MODEL_NAME := models/llama-midi.pth/


# ==============================================================================
# 開発 & デプロイ ワークフロー
# ==============================================================================

## 🚀 本番環境向けデプロイ (5 variations)
.PHONY: deploy-production
deploy-production: lock
	@echo "🚀 --- Starting PRODUCTION deployment --- 🚀"
	@$(MAKE) generate-cache-prod
	@$(MAKE) sync-s3
	@echo "✅ --- PRODUCTION deployment finished! --- ✅"

## 🛠️ 開発環境向けデプロイ (2 variations)
.PHONY: deploy-development
deploy-development: lock
	@echo "🛠️ --- Starting DEVELOPMENT deployment --- 🛠️"
	@$(MAKE) generate-cache-dev
	@$(MAKE) sync-s3
	@echo "✅ --- DEVELOPMENT deployment finished! --- ✅"

## 💻 ローカル開発サーバーの起動 (uv)
.PHONY: dev-server
dev-server:
	@echo "🔥 --- Starting local API server on http://localhost:8000 ---"
	uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir src

## 🐳 ローカル開発サーバーの起動 (Docker + Nginxキャッシュ)
.PHONY: dev-server-docker
dev-server-docker: lock
	@echo "🐳 --- Starting local API server with Docker Compose on http://localhost:8000 ---"
	docker compose up --build

# --- ヘルパーターゲット (デプロイ) ---

.PHONY: generate-cache-prod generate-cache-dev sync-s3

generate-cache-prod:
	@echo "🏭 Building PRODUCTION Docker image..."
	docker build --build-arg APP_ENV=production -t $(DOCKER_IMAGE_PROD) -f Dockerfile.generate .
	@echo "🔥 Running PRODUCTION cache generation (5 variations)..."
	docker run --gpus all --rm -u "$(id -u):$(id -g)" -v ./dist:/app/dist $(DOCKER_IMAGE_PROD)

generate-cache-dev:
	@echo "🏭 Building DEVELOPMENT Docker image..."
	docker build --build-arg APP_ENV=development -t $(DOCKER_IMAGE_DEV) -f Dockerfile.generate .
	@echo "🔥 Running DEVELOPMENT cache generation (2 variations)..."
	docker run --gpus all --rm -u "$(id -u):$(id -g)" -v ./dist:/app/dist $(DOCKER_IMAGE_DEV)

sync-s3:
	@if [ ! -d "./dist" ]; then \
		echo "❌ Error: ./dist directory not found. Run 'make deploy-...' first."; \
		exit 1; \
	fi
	@echo "📡 --- Syncing ./dist to S3 bucket: $(S3_BUCKET_NAME)... ---"
	aws s3 sync --profile $(AWS_PROFILE_NAME) ./dist s3://$(S3_BUCKET_NAME)/api/
	@echo "✅ --- Sync to S3 complete. ---"


# ==============================================================================
# 依存関係管理
# ==============================================================================

## ⚙️ 開発環境のセットアップ (依存関係のインストールとプロジェクトのリンク)
.PHONY: setup
setup:
	@echo "⚙️ --- Setting up development environment ---"
	@uv sync --locked
	@uv pip install -e .
	@echo "✅ --- Setup complete. ---"

## 🔒 pyproject.tomlからuv.lockを再生成する
.PHONY: lock
lock:
	@echo "🔒 Locking dependencies with --all-extras..."
	uv lock
	@echo "✅ uv.lock has been updated."


# ==============================================================================
# モデル学習 & DVC
# ==============================================================================

## 🔄 DVCパイプラインの再実行
.PHONY: repro
repro: check_commit PIPELINE.md
	uv run dvc repro
	git commit dvc.lock -m 'run dvc repro' || true

## 📝 パイプラインスナップショットの更新
PIPELINE.md: dvc.yaml params.yaml
	echo '# pipeline' > $@
	echo '' >> $@
	echo '## stages' >> $@
	echo '' >> $@
	uv run dvc dag --md >> $@
	echo '' >> $@
	echo '## files' >> $@
	echo '' >> $@
	uv run dvc dag --md --outs >> $@
	git commit $@ -m 'update pipeline' || true

## 🧐 Gitのワーキングディレクトリがクリーンかチェック
.PHONY: check_commit
check_commit:
	git diff --exit-code
	git diff --exit-code --staged


# ==============================================================================
# コード品質 & テスト
# ==============================================================================

## 💅 コードのフォーマットとLintチェック
.PHONY: lint
lint:
	@echo "💅 --- Formatting and linting code... ---"
	uv run ruff format src tests/*.py
	uv run ruff check --fix src tests/*.py

## ✅ テストの実行 (Python と JavaScript)
.PHONY: test
test: test-py test-js

## 🐍 Python テストの実行
.PHONY: test-py
test-py:
	@echo "🐍 --- Running Python tests... ---"
	@pyenv exec python -m pytest

## 📜 JavaScript テストの実行 (Docker内)
.PHONY: test-js
test-js:
	@echo "📜 --- Running JavaScript tests in Docker... ---"
	@sudo docker build --target node-test -t melody-flow-js-test .
	@echo "✅ --- JavaScript tests complete. ---"


# ==============================================================================
# その他
# ==============================================================================

## 🧹 生成物のクリーンアップ
.PHONY: clean
clean:
	@echo "🧹 --- Cleaning up generated files and Docker images... ---"
	rm -rf ./dist
	@docker image rm $(DOCKER_IMAGE_PROD) || true
	@docker image rm $(DOCKER_IMAGE_DEV) || true
	@echo "✅ --- Cleanup complete. ---"
