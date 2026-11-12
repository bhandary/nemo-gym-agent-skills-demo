.PHONY: demo test

demo:
	./run_demo.sh

test:
	. .venv/bin/activate && python -m pytest -q
