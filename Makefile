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


## inferance
inferance:
	uv run python -m src.inferance models/llama-midi.pth/ \
    'Title: Anthropology Chords:  Bb6 G7 C-7 F7 Bb G-7 F-7 Bb7 Eb7 Ab7 D-7 D7 C7'

## inferance
inferance-llama32:
	uv run python -m src.inferance models/llama-3.2-1b.pth/ \
    'Title: Anthropology Chords:  Bb6 G7 C-7 F7 Bb G-7 F-7 Bb7 Eb7 Ab7 D-7 D7 C7'


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
