#!/bin/bash

# # makeコマンドを実行
# make gcd_euclid

# # ビルドの成功を確認
# if [ $? -ne 0 ]; then
#     echo "エラー: ビルドに失敗しました。" >&2
#     exit 1
# fi

# 必要なファイルが生成されたか確認
required_files=("gcd_euclid.o" "main_euclid.o" "gcd_euclid")
for file in "${required_files[@]}"; do
    if [ ! -f "$file" ]; then
        echo "エラー: $file が生成されていません。" >&2
        exit 1
    fi
done

# gcd_euclid.oを解析してgcd_euclid関数が定義されているか確認
if ! nm gcd_euclid.o | grep -q " T gcd_euclid"; then
    echo "エラー: gcd_euclid.o内にgcd_euclid関数が定義されていません。" >&2
    exit 1
fi

echo "confirm the existence of gde_euclid.o, main_euclid.o, main_euclid and that gcd_eulid function is implemented on gcd_euclid.c"
exit 0
