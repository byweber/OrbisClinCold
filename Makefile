# OrbisClin Cold — atalhos de desenvolvimento
ifeq ($(OS),Windows_NT)
  PY  = .venv\Scripts\python
  PIP = .venv\Scripts\pip
else
  PY  = .venv/bin/python
  PIP = .venv/bin/pip
endif

.PHONY: run worker beat test migrate lint

run:
	$(PY) -m uvicorn app.main:app --reload --port 8001

worker:
	$(PY) -m celery -A app.core.worker worker -l info -c 4

beat:
	$(PY) -m celery -A app.core.worker beat -l info

test:
	$(PY) -m pytest tests/ -v

migrate:
	$(PY) -m alembic revision --autogenerate -m "$(m)"
	$(PY) -m alembic upgrade head

lint:
	$(PY) -m py_compile $(shell find app -name "*.py")
	@echo "Sintaxe OK"
