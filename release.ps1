#!/bin/sh
#Requires -Version 7

# This is a polyglot script that runs in both a POSIX compliant shell and PowerShell 7+.
# It assumes the following prerequisites have been met:
# 1. uv is installed via the standalone installer and in PATH
#    (set UV_NO_MODIFY_PATH=1 when installing: https://github.com/astral-sh/uv/issues/10413)
# 2. Node.js is installed and in PATH
# 3. The current working directory is set to the project root
# 4. The environment variable SC_GITHUB_TOKEN is set to a valid GitHub token
# 5. A compatible Python virtual environment is activated
# The shell commands are separated into blocks by the stages in the software testing life cycle:
# 1. development
#   1.1. dependency management
#   1.2. code generation
#   1.3. linting
# 2. system integration testing
# 3. user acceptance testing
# 4. production

uv self update &&
uv tool install --upgrade security-constraints &&
npm install pyright@latest &&
uv tool run security-constraints --min-severity moderate --output ./constraints.txt &&
uv pip compile --constraints ./constraints.txt --output-file ./requirements.txt ./pyproject.toml &&
uv pip sync ./requirements.txt &&
uv pip install --editable . --constraints ./constraints.txt --constraints ./requirements.txt --group all &&

python -m openapi_spec_validator --subschema-errors all --validation-errors all ./resources/openapi/openapi.yaml &&
python -m datamodel_code_generator &&

python -m ruff check &&
python -m pylint ./src/ ./tests/ &&
npm exec pyright &&

python -m pytest &&

python -m mprof run --include-children ./src/stackexchange/backup.py --account-id 8 &&
python -m mprof peak &&
python -m mprof clean &&

python -m bumpver update --patch --no-fetch &&
python -m validate_pyproject ./pyproject.toml &&

$(exit)
