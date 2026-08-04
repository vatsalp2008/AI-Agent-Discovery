.DEFAULT_GOAL := help
.PHONY: help install seed run search stats test lint fix check docker-build docker-up docker-down clean

PYTHON ?= python
APP_DIR := ai-agent-discovery

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install:  ## Install runtime and development dependencies
	$(PYTHON) -m pip install -r $(APP_DIR)/requirements-dev.txt

seed:  ## Build the FAISS index from data/agents.json
	$(PYTHON) $(APP_DIR)/seed.py

run:  ## Start the web app
	$(PYTHON) $(APP_DIR)/frontend/app.py

search:  ## Search from the terminal, e.g. make search Q="write python"
	$(PYTHON) $(APP_DIR)/cli.py "$(Q)"

stats:  ## Print index statistics
	$(PYTHON) $(APP_DIR)/cli.py --stats

test:  ## Run the test suite
	$(PYTHON) -m pytest

lint:  ## Check formatting and lint rules
	$(PYTHON) -m ruff check .

fix:  ## Apply the lint fixes that can be applied automatically
	$(PYTHON) -m ruff check . --fix

check: lint test  ## Run lint and tests, as CI does

docker-build:  ## Build the container image
	docker build -t ai-agent-discovery .

docker-up:  ## Start Ollama, seed the index, and run the app
	docker compose up --build

docker-down:  ## Stop the compose stack
	docker compose down

clean:  ## Remove caches and the generated index
	rm -rf .pytest_cache .ruff_cache data/faiss_index
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
