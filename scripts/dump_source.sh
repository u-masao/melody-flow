#!/bin/bash

clear

FILES=(
#Dockerfile
#Dockerfile.generate
#LICENSE.md
#Makefile
#PIPELINE.md
#README.md
#data/external/.gitkeep
#data/interim/.gitkeep
#data/processed/.gitkeep
#data/raw/.gitignore
#data/raw/.gitkeep
#docker-compose.yaml
#docs/architecture.md
#docs/deplow_guide_to_aws.md
#docs/plan_of_architecture_enhance.md
docs/project_summary.md
#dvc.lock
#dvc.yaml
#nginx/nginx.conf
#nginx/nginx_http_cache.conf
#nginx/nginx_http_only.conf
#nginx/nginx_https.conf
#params.yaml
#pyproject.toml
#scripts/dump_source.sh
#scripts/warmup.sh
#src/api/__init__.py
#src/api/main.py
#src/eda/__init__.py
#src/eda/data_viewer.py
#src/model/__init__.py
#src/model/chord_name_parser.py
#src/model/inference.py
#src/model/make_dataset.py
#src/model/melody_processor.py
#src/model/train_model.py
#src/warmup/__init__.py
#src/warmup/generate_static_cache.py
#src/warmup/generate_warmup_data.py
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

echo 'コードを修正したら必ず全文を表示して'
