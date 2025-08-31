##############################################################################
# Globals
##############################################################################

PORT=7860

##############################################################################
# servers
##############################################################################

## run ui and api
ui:
api:
	uv run uvicorn src.api:app --reload --host 0.0.0.0 --port $(PORT)

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

