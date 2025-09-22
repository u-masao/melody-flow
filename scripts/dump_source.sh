#!/bin/bash

clear

FILES=(
#Dockerfile
#Dockerfile.generate
#LICENSE.md
#Makefile
#PIPELINE.md
#README.md
#docker-compose.yaml
#docs/architecture.md
#docs/deploy_guide_to_aws.md
#docs/plan_of_architecture_enhance.md
#docs/play-mode-ui.png
docs/project_summary.md
#docs/studio-mode-ui.png
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
src/model/evaluate.py
src/model/audio.py
#src/model/inference.py
#src/model/make_dataset.py
#src/model/melody_processor.py
#src/model/train_model.py
src/model/utils.py
#src/warmup/__init__.py
#src/warmup/generate_static_cache.py
#static/app.html
#static/favicon.svg
#static/index.html
#static/main.js
#static/midi-test.html
#static/presentation.html
#tests/__init__.py
#tests/test_chord_name_parser.py
#tests/test_melody_processor.py
#tests/test_model_evaluate.py
#tests/test_model_utils.py
#uv.lock
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
