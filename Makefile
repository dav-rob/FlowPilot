.PHONY: setup build run dev test validate
setup:
	python3 -m venv .venv
	.venv/bin/python -m pip install -e '.[dev]'
	npm --prefix frontend install
build:
	npm --prefix frontend run build
run:
	.venv/bin/python -m flowpilot
dev:
	npm --prefix frontend run dev
test:
	.venv/bin/python -m pytest -q
validate:
	.venv/bin/python -m flowpilot_data validate --root .
