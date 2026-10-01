FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# INSTALL_DEV=true のときだけ pytest・black・ruff などの開発用パッケージも入れる
# （ローカルの docker-compose.yml で true にしている。本番用のイメージには入れない）
ARG INSTALL_DEV=false
COPY scraper/requirements.txt scraper/requirements-dev.txt ./
RUN if [ "$INSTALL_DEV" = "true" ]; then \
        pip install --no-cache-dir -r requirements-dev.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

COPY scraper/ .

CMD ["python", "-m", "scraper.main"]
