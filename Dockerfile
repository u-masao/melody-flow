FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    git

COPY requirements.txt .
# UnslothはPyTorchのバージョンに依存するため、ここで指定
RUN pip install torch==2.1.2+cu121 torchaudio==2.1.2+cu121 --index-url https://download.pytorch.org/whl/cu121
RUN pip install -r requirements.txt

COPY ./src /app/src
COPY ./models /app/models

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
