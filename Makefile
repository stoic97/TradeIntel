.PHONY: help hash-check hash-lock test-repro test lint clean

PREREG := services/research/prereg/framework_v1.yaml

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

hash-check: ## Verify the pre-commitment file matches its committed hash
	@shasum -a 256 -c $(PREREG).sha256

hash-lock: ## Write the hash of the pre-commitment file (kickoff only; CEO sign-off)
	@shasum -a 256 $(PREREG) > $(PREREG).sha256 && cat $(PREREG).sha256

test-repro: ## Run every transformation twice; hashes must match
	pytest tests/reproducibility -x -q

test: ## Run all tests
	pytest tests -x -q

lint: ## Lint Python
	ruff check .

clean: ## Remove caches
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -exec rm -rf {} + 2>/dev/null || true

.dev-env: ## Local keys and paths, generated once and kept (gitignored)
	@python -c "import secrets; from services.production.accounts.file_store import generate_key; \
print('SCOPE_SECRET_KEY=' + secrets.token_urlsafe(48)); \
print('SCOPE_FILE_KEY=' + generate_key()); \
print('SCOPE_DB=sqlite:///./scope.db'); \
print('SCOPE_FILES=./_files')" > .dev-env
	@echo "wrote .dev-env — local keys, never committed."
	@echo "The file key must stay put: change it and files already uploaded stop decrypting."

run: .dev-env ## Start the app on http://127.0.0.1:8000 with reload
	@python -c "import uvicorn" 2>/dev/null || \
		(echo "uvicorn is not installed in this environment: uv add uvicorn"; exit 1)
	@set -a && . ./.dev-env && set +a && \
		python -m services.production.api.cli init-db && \
		uvicorn services.production.api.app:create_app --factory \
			--reload --host 127.0.0.1 --port 8000

dev-seed: .dev-env ## Mint a local invite code (CODE=DEV-1 by default)
	@set -a && . ./.dev-env && set +a && \
		python -m services.production.api.cli invite --code $(or $(CODE),DEV-1)
