# ==============================================================================
# 変数
# ==============================================================================

include .env

AWS_PROFILE_NAME := melody-flow
S3_BUCKET_NAME := melody-flow.click
GENERATOR_DOCKER_IMAGE := "melody-flow-generator"


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
	MODEL_NAME=$(MODEL_NAME) uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir src

## 🐳 ローカル開発サーバーの起動 (Docker + Nginxキャッシュ)
.PHONY: dev-server-docker
dev-server-docker: lock
	@echo "🐳 --- Starting local API server with Docker Compose on http://localhost:8000 ---"
	MODEL_NAME=$(MODEL_NAME) docker compose up --build

# --- ヘルパーターゲット (デプロイ) ---

.PHONY: generate-build-image generate-cache-prod generate-cache-dev sync-s3

generate-build-image:
	@echo "🏭 Building PRODUCTION Docker image..."
	docker build -t $(GENERATOR_DOCKER_IMAGE) -f Dockerfile.generate .

generate-cache-prod: generate-build-image
	@echo "🔥 Running PRODUCTION cache generation (5 variations)..."
	docker run --gpus all --rm -v ./dist:/app/dist \
	-e MODEL_NAME=$(MODEL_NAME) \
	-e APP_ENV=production --env-file .env $(GENERATOR_DOCKER_IMAGE)

generate-cache-dev: generate-build-image
	@echo "🔥 Running DEVELOPMENT cache generation (2 variations)..."
	docker run --gpus all --rm -v ./dist:/app/dist \
	-e MODEL_NAME=$(MODEL_NAME) \
	-e APP_ENV=development --env-file .env $(GENERATOR_DOCKER_IMAGE)

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

## ✅ テストの実行
.PHONY: test
test:
	@echo "✅ --- Running tests... ---"
	uv run pytest tests


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
