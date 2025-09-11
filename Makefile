##############################################################################
# Globals
##############################################################################

PORT=7860

##############################################################################
# servers
##############################################################################

# export MODEL_NAME:=dx2102/llama-midi
export MODEL_NAME:=models/llama-midi.pth/

## run ui and api
ui:
api:
	uv run uvicorn src.api.main:app --reload --host 0.0.0.0 --port $(PORT)

## test api
test_api:
	time curl -X POST "http://localhost:$(PORT)/generate" -H "Content-Type: application/json" -d '{"chord_progression": "C - G - Am - F", "style": "POP風"}'


##############################################################################
# finetuning
##############################################################################

## run training pipeline
repro: check_commit PIPELINE.md
	uv run dvc repro
	git commit dvc.lock -m 'run dvc repro' || true

## check commieted
check_commit:
	git diff --exit-code
	git diff --exit-code --staged

## write pipeline snapshot
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


## inference
inference:
	uv run python -m src.model.inference models/llama-midi.pth/ \
    '{"chord_progression": "Bb6 G7 C-7 F7 Bb G-7 F-7 Bb7 Eb7 Ab7 D-7 D7 C7"}'

## inference
inference-llama32:
	uv run python -m src.model.inference models/llama-3.2-1b.pth/ \
    '{"chord_progression": "Bb6 G7 C-7 F7 Bb G-7 F-7 Bb7 Eb7 Ab7 D-7 D7 C7"}'


##############################################################################
# tools 
##############################################################################

## code formatting
lint:
	uv run ruff check --fix src tests
	uv run ruff format src tests

## test
test:
	uv run pytest tests

## generate requirements.txt
requirements.txt:
	uv pip compile pyproject.toml -o requirements.txt --generate-hashes


##############################################################################
# Cache Management for LLM API (Phase 1)
##############################################################################

# --- Variables ---
# docker-compose.yamlで定義したボリューム名を直接指定
CACHE_VOLUME_NAME := nginx_cache_data
EXPORT_FILE := nginx_cache.tar.gz
REMOTE_HOST := user@remote.server.com
REMOTE_PATH := /tmp/nginx_cache_import/

# --- Targets ---
.PHONY: warmup cache-export cache-copy cache-import cache-all

cache-all: warmup cache-export cache-copy cache-import
	@echo "All cache management tasks completed."

generate-warmup-data:
	@echo "Installing dependencies from pyproject.toml..."
	@uv pip sync pyproject.toml
	@echo "Generating data for cache warmup..."
	@uv run python -m src.warmup.generate_warmup_data

warmup: generate-warmup-data
	@echo "Warming up Nginx cache..."
	@./scripts/warmup.sh
	@echo "Cache warmup complete."

cache-export:
	@echo "Exporting cache data from volume [$(CACHE_VOLUME_NAME)] to [$(EXPORT_FILE)]..."
	@docker run --rm \
		-v $(CACHE_VOLUME_NAME):/cache_data \
		-v $(CURDIR):/backup \
		alpine tar czf /backup/$(EXPORT_FILE) -C /cache_data .
	@echo "Cache data exported successfully."

cache-copy:
	@echo "Copying [$(EXPORT_FILE)] to [$(REMOTE_HOST)]..."
	@scp $(EXPORT_FILE) $(REMOTE_HOST):/tmp/
	@echo "File copied successfully."

cache-import:
	@echo "Importing cache data on remote machine..."
	@ssh $(REMOTE_HOST) ' \
		mkdir -p $(REMOTE_PATH) && \
		tar xzf /tmp/$(EXPORT_FILE) -C $(REMOTE_PATH) && \
		docker volume create $(CACHE_VOLUME_NAME) && \
		docker run --rm \
			-v $(CACHE_VOLUME_NAME):/new_cache \
			-v $(REMOTE_PATH):/backup \
			alpine sh -c "cp -a /backup/. /new_cache/" && \
		rm -rf /tmp/$(EXPORT_FILE) $(REMOTE_PATH) && \
		echo "Remote cache import complete." \
	'
