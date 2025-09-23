#!/bin/bash

clear

FILES=`cat .dump_files | grep -v '^#'`

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
