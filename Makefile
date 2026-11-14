.PHONY: help hash-check hash-lock test test-fast test-repro lint clean run

PREREG := services/research/prereg/framework_v1.yaml
# Every Python tool runs through uv, as the docs do: no activated venv needed (TICKET-929).
UV := uv run
# pytest takes -q from pyproject's addopts. Do not add another: -qq drops the final count
# line, and a run that does not say how many passed cannot be checked.

help: ## Show available commands
	@grep -E '^[a-zA-Z_.-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

hash-check: ## Verify the pre-commitment file against its locked hash (says "not locked yet" before the lock)
	@$(UV) python scripts/hash_check.py

hash-lock: ## Write the hash of the pre-commitment file (kickoff only; CEO sign-off)
	@shasum -a 256 $(PREREG) > $(PREREG).sha256 && cat $(PREREG).sha256

test: ## Run the whole suite to the end (the deploy check; what CI runs)
	$(UV) pytest tests

test-fast: ## Run the suite, stopping at the first failure (local use)
	$(UV) pytest tests -x

test-repro: ## Run every transformation twice; hashes must match
	$(UV) pytest tests/reproducibility

lint: ## Lint Python
	$(UV) ruff check .

clean: ## Remove caches (__pycache__, pytest, ruff, mypy, hypothesis)
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name .mypy_cache -o -name .hypothesis \) -prune -exec rm -rf {} + 2>/dev/null || true

.dev-env: ## Local keys and paths, generated once and kept (gitignored)
	@$(UV) python -c "import secrets; from services.production.accounts.file_store import generate_key; \
print('SCOPE_SECRET_KEY=' + secrets.token_urlsafe(48)); \
print('SCOPE_FILE_KEY=' + generate_key()); \
print('SCOPE_DB=sqlite:///./scope.db'); \
print('SCOPE_FILES=./_files')" > .dev-env
	@echo "wrote .dev-env — local keys, never committed."
	@echo "The file key must stay put: change it and files already uploaded stop decrypting."

run: .dev-env ## Start the app on http://127.0.0.1:8000 with reload
	@set -a && . ./.dev-env && set +a && \
		$(UV) python -m services.production.api.cli init-db && \
		$(UV) uvicorn services.production.api.app:create_app --factory \
			--reload --host 127.0.0.1 --port 8000
