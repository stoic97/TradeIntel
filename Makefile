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
