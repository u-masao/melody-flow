#!/bin/bash

clear

FILES=(
docs/project_summary.md
docs/architecture.md
docs/deplow_guide_to_aws.md
docs/plan_of_architecture_enhance.md
src/model/make_dataset.py
src/model/train_model.py
src/model/inferance.py
src/model/chord_name_parser.py
src/model/melody_processor.py
src/api/main.py
static/index.html
static/presentation.html
static/app.html
static/main.js
pyproject.toml
Makefile
docker-compose.yaml
Dockerfile
nginx/nginx_https.conf
nginx/nginx_http_only.conf
nginx/nginx.conf
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
