#!/bin/bash

FILES=(
docs/project_summary.md
docs/architecture.md
src/model/make_dataset.py
src/model/train_model.py
src/model/inferance.py
src/model/chord_name_parser.py
src/model/melody_processor.py
src/api/main.py
static/index.html
static/app.html
static/main.js
static/presentation.html
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
