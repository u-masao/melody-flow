PORT=7860

api:
	uv run uvicorn src.api:app --reload --host 0.0.0.0 --port $(PORT)

test_api:
	time curl -X POST "http://localhost:$(PORT)/generate" -H "Content-Type: application/json" -d '{"chord_progression": "C - G - Am - F", "style": "POP風"}'


repro: PIPELINE.md check_commit
	uv run dvc repro

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

check_commit:
	git diff --exit-code
	git diff --exit-code --stages
