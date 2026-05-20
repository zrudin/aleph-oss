.PHONY: help install run dev test lint format vault-create vault-mount vault-unmount vault-wipe ollama-pull clean

VAULT_SPARSEBUNDLE ?= $(HOME)/Library/PersonalAssistant/PA-Vault.sparsebundle
VAULT_MOUNT ?= /Volumes/PA-Vault

help:
	@echo "Personal Assistant — common tasks"
	@echo ""
	@echo "  make install        Install Python deps via uv"
	@echo "  make run            Mount the encrypted vault, run the server, unmount on exit"
	@echo "  make dev            Run the server against an unencrypted dev vault in ./.dev-vault/"
	@echo "  make test           Run pytest"
	@echo "  make lint           Run ruff"
	@echo "  make format         Run ruff format"
	@echo ""
	@echo "  make vault-create   Create the encrypted sparsebundle (one-time)"
	@echo "  make vault-mount    Mount the vault at $(VAULT_MOUNT)"
	@echo "  make vault-unmount  Unmount the vault"
	@echo "  make vault-wipe     Delete ./.dev-vault/ so the next \`make dev\` starts fresh"
	@echo "  make ollama-pull    Pull the chat + embedding models"

install:
	uv sync --extra dev

run:
	./scripts/run.sh

dev:
	./scripts/run-dev.sh

test:
	uv run pytest -q

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

vault-create:
	./scripts/vault-create.sh

vault-mount:
	./scripts/vault-mount.sh

vault-unmount:
	./scripts/vault-unmount.sh

vault-wipe:
	./scripts/vault-wipe.sh

ollama-pull:
	./scripts/ollama-pull.sh

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .ruff_cache .pytest_cache build dist *.egg-info
