# ベースイメージとしてPython 3.9を使用
FROM python:3.12.4-slim

# 作業ディレクトリの設定
WORKDIR /app

# dockerizeのバージョンを環境変数として設定
ENV DOCKERIZE_VERSION v0.8.0

# dockerizeをダウンロードしてインストール
RUN apt-get update \
    && apt-get install -y wget \
    && wget -O - https://github.com/jwilder/dockerize/releases/download/$DOCKERIZE_VERSION/dockerize-linux-amd64-$DOCKERIZE_VERSION.tar.gz | tar xzf - -C /usr/local/bin \
    && apt-get autoremove -yqq --purge wget && rm -rf /var/lib/apt/lists/*

# 必要なPythonライブラリのインストール
# (pyproject.tomlからryeによって自動生成されたrequirements.lockを使用)
# 参考: https://rye.astral.sh/guide/docker/
COPY requirements.lock requirements/requirements.lock
RUN PYTHONDONTWRITEBYTECODE=1 pip install --no-cache-dir -r requirements/requirements.lock

# アプリケーションのソースコードをコピー
# COPY src/ .

# FastAPIアプリケーションの起動
CMD ["dockerize", "-wait", "tcp://db:3306", "-timeout", "30s", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
