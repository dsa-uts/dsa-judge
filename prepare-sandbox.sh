#!/bin/bash

set -e

SCRIPT_DIR=$(cd $(dirname $0); pwd)

# サンドボックスコンテナのCPUを隔離
# Linux以外にも対応するために、この処理は行わない
# この設定はサンドボックスのパフォーマンスを高くするために行うものであるため、特に必要不可欠でもない
# mkdir -p /sys/fs/cgroup/judge.slice/
# systemctl set-property judge.slice AllowedCPUs=0-1
# echo 'isolated' > /sys/fs/cgroup/judge.slice/cpuset.cpus.partition

# crunのインストール
if ! which crun > /dev/null 2>&1; then
    echo "crunがインストールされていません。インストールを開始します。"
    wget https://github.com/containers/crun/releases/download/1.17/crun-1.17-linux-amd64 -O /usr/local/bin/crun
    chmod +x /usr/local/bin/crun
    echo "crunのインストールが完了しました。"
    # dockerの設定(デフォルトランタイムをcrunにする)
    # /etc/dockerがない場合は作成、ある場合でもエラーにならないようにする
    mkdir -p /etc/docker
    cp $SCRIPT_DIR/docker-daemon.json /etc/docker/daemon.json

    # dockerの再起動
    systemctl restart docker
else
    echo "crunは既にインストールされています。"
fi
