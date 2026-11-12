.PHONY: demo test ui

demo:
	./run_demo.sh

test:
	. .venv/bin/activate && python -m pytest -q

ui:
	./run_ui.sh
