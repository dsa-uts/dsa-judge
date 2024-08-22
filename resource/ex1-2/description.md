# 基本課題
二つの整数$N$と$M$を受け取り、その最大公約数を出力するプログラム`gcd_recursive`を作成せよ。アルゴリズムはユークリッドの互除法に基づいた再帰的アルゴリズムとすること。

## 制約
* フォーマットチェック時: $1 \leq N,M \leq 100$
* 採点時: $1 \leq N,M \leq 2\times10^{9}$

## 入力
プログラムは以下の形式で実行される。NとMは整数である。

>
> ./gcd_recursive N M
>

## 出力
入力が想定した形式であり、かつ制約を満たしているならば$N$と$M$の最大公約数を出力せよ。
このときプログラムの戻り値は`0`とする。

そうでないならば、標準エラー出力にエラーメッセージを出すこと。
このときプログラムの戻り値は`1` (`EXIT_FAILURE`と同じ) とする。

# 提出方法
`Makefile`, `gcd_recursive.c`, `main_recursive.c`の3点を提出せよ。
* `Makefile` : 以下の内容が含まれているビルドスクリプト
```Makefile
gcd_recursive: gcd_recursive.o main_recursive.o
```
* `gcd_recursive.c` : ユークリッドの互除法の再帰的アルゴリズムに基づく関数`gcd_recursive`が定義されているCプログラム
* `main_recursive.c` : `main`関数が定義されているCプログラム
