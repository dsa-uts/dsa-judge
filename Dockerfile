# ベースイメージとしてPython 3.9を使用
FROM python:3.12.4-slim

# 作業ディレクトリの設定
WORKDIR /app

# ------------- Dockerクライアントのみのインストール ---------------------------------
# 参考: https://docs.docker.com/engine/install/debian/#install-using-the-repository
# Add Docker's official GPG key:
RUN apt-get update && \
    apt-get install ca-certificates curl -y && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -4fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc
  
# Add the repository to Apt sources:
RUN echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
    tee /etc/apt/sources.list.d/docker.list > /dev/null
RUN apt-get update
RUN apt-get install docker-ce-cli -y
# ------------------------------------------------------------------------------

# 必要なPythonライブラリのインストール
# (pyproject.tomlからryeによって自動生成されたrequirements.lockを使用)
# 参考: https://rye.astral.sh/guide/docker/
COPY requirements.lock requirements/requirements.lock
RUN PYTHONDONTWRITEBYTECODE=1 pip install --no-cache-dir -r requirements/requirements.lock

# アプリケーションのソースコードをコピー
# COPY src/ .

# FastAPIアプリケーションの起動
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
