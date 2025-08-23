

PORT=7860

api:
	uv run uvicorn src.api:app --reload --host 0.0.0.0 --port $(PORT)

test_api:
	time curl -X POST "http://localhost:$(PORT)/generate" -H "Content-Type: application/json" -d '{"chord_progression": "C - G - Am - F", "style": "POP風"}'
