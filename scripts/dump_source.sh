#!/bin/bash

clear

grep -v '^#' .dump_files | while read -r file
do
    echo "## $file"
    echo ""
    echo '```'
    cat $file
    echo '```'
    echo ""
done

echo 'ファイルを修正したら、必ず修正したファイルの全文を表示して'
