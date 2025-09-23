#!/bin/bash

clear

FILES=(
#README.md
docs/project_summary.md
static/app.html
#static/favicon.svg
#static/index.html
static/main.js
#static/midi-test.html
#static/presentation.html
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

echo 'ファイルを修正したら、必ず修正したファイルの全文を表示して'
