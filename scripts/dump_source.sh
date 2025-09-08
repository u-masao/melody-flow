#!/bin/bash

FILES=(
docs/project_summary.md
docs/architecture.md
src/chord_name_parser.py
src/melody_processor.py
src/api.py
src/make_dataset.py
src/train_model.py
src/inferance.py
static/index.html
static/main.js
static/presentation.html
static/site.html
)

for ((i=0; i<${#FILES[@]}; i++))
do
    echo "## ${FILES[$i]}"
    echo ""
    echo '```'
    cat ${FILES[$i]}
    echo '```'
    echo ""
done
