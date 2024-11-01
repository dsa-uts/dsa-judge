FROM ubuntu:24.10

RUN apt update && apt install -y gcc g++ nlohmann-json3-dev
