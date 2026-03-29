# Knowledge Directory

This directory is the public scaffold for the Harness-owned canonical pipeline
root.

Subdirectories:

- `raw/` stores original inputs and extraction metadata
- `normalized/` stores structured facts
- `curated/` stores distilled insights and consensus tracking

Public repository rule:

- keep the directory structure in git
- keep local knowledge contents out of git
- connect external upstream knowledge sources through `config/local/runtime.json`
