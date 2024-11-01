#!/usr/bin/env bash

set -e

SCRIPT_DIR=$(cd $(dirname $0); pwd)

# builderイメージをビルド
docker build -t builder-watchdog -f $SCRIPT_DIR/Dockerfile.builder $SCRIPT_DIR

# watchdog.cppのコンパイル
docker run --rm -it -v $SCRIPT_DIR:/work --workdir /work builder-watchdog \
  bash -c "g++ -o watchdog watchdog.cpp"

# GCCを使えるsandboxイメージをビルド
docker build -t checker-lang-gcc -f $SCRIPT_DIR/Dockerfile.GCC $SCRIPT_DIR

# 実行用のsandboxイメージをビルド
docker build -t binary-runner -f $SCRIPT_DIR/Dockerfile.binary-runner $SCRIPT_DIR
