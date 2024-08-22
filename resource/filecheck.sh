#!/bin/bash

# 引数からファイルリストを受け取る
files=("$@")

# 引数が指定されていない場合はエラーメッセージを表示して終了
if [ ${#files[@]} -eq 0 ]; then
    echo "エラー: ファイル名を引数として指定してください。" >&2
    exit 1
fi

# 全てのファイルが存在するかチェック
all_exist=true
for file in "${files[@]}"; do
    if [ ! -f "$file" ]; then
        echo "エラー: $file が見つかりません。" >&2
        all_exist=false
    fi
done

# 結果の出力
if $all_exist; then
    echo "good"
else
    exit 1
fi
