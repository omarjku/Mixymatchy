.PHONY: install build precompute backend frontend eval redteam test

install:
	pip install -r backend/requirements.txt
	cd frontend && npm install

build:
	python3 -m pipeline.build
	python3 -m compare.build

# LLM path only (SECOND_LOOK_BACKEND=llm)
precompute:
	cd backend && python -m app.precompute

backend:
	uvicorn --app-dir backend app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

eval:
	python3 -m eval.run
	python3 -m eval.run_api

# leak measurement on attack/non-task inputs; LLM=1 turns the LLM layer on (needs ANTHROPIC_API_KEY)
redteam:
	python3 -m eval.redteam.run $(if $(LLM),--llm,)

test:
	python3 -m engine.kb > /dev/null
	python3 -m unittest security.test_security
	python3 -m unittest engine.test_engine engine.test_kb engine.test_relevance engine.test_clinical_gate engine.test_llm engine.test_request engine.test_intent engine.test_keyfacts engine.test_ask compare.test_compare eval.test_eval
	cd backend && python3 -m pytest -q
