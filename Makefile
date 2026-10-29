.PHONY: install precompute backend frontend eval test

install:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

precompute:
	cd backend && python -m app.precompute

backend:
	cd backend && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

eval:
	python eval/run.py

test:
	cd backend && python -m pytest -q
