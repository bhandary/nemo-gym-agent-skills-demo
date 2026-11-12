# Recorded sample

This folder is a finished run of `./run_demo.sh` captured on 2026-11-12.

It is **mock output**. The policy model was `mock-desk-associate` on `http://127.0.0.1:43117/v1`, through NeMo Gym's `vllm_model` adapter. NeMo Gym was 0.7.0 on Python 3.13.14. No NVIDIA, OpenAI, or other live model was called. See [manifest.json](manifest.json).

Open [comparison.md](comparison.md) for the table and [trace.md](trace.md) for the dented-kettle episode. The JSONL files are the rollouts Gym wrote. `logs/` is the `gym eval run` output for each variant.

A later run with your own API key writes `results/` and does not replace this folder.
