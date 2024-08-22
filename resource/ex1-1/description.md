# 基本課題
二つの整数$N$と$M$を受け取り、その最大公約数を出力するプログラム`gcd_euclid`を作成せよ。アルゴリズムはユークリッドの互除法に基づいて計算すること。

## 制約
* フォーマットチェック時: $1 \leq N,M \leq 100$
* 採点時: $1 \leq N,M \leq 2\times10^{9}$

## 入力
プログラムは以下の形式で実行される。NとMは必ず整数であることが保証される。

>
> ./gcd_euclid N M
>

## 出力
入力された二つの整数$N$と$M$が制約を満たしているならばそれらの最大公約数を以下の形式で標準入力に出力せよ
>
> The GCD of [N] and [M] is [gcd of N and M].
>
このときプログラムの戻り値は`0`とする。

なお、入力として以下の例外が与えられる場合がある
1. 引数が2つ以上与えられる
2. $N$または$M$にゼロ以下の値が与えられる

1つめのケースに対しては、標準エラー出力に以下の形式のメッセージを出力すること。
```
Usage: ./gcd_euclid <number1> <number2>
```
2つめのケースに対しては、標準エラー出力に以下の形式のメッセージを出力すること。
```
Two number must be greater than 0.
```
1と2両方のケースに対して、戻り値は1(`EXIT_FAILURE`と同じ)とすること。

## 具体例

```
$ ./gcd_euclid 15 30
The GCD of 15 and 30 is 15.
$ ./gcd_euclid 35 51
The GCD of 35 and 51 is 1.
```

# 提出方法
`Makefile`, `gcd_euclid.c`, `main_euclid.c`の3点を提出せよ。
* `Makefile` : 以下の内容が含まれたビルドスクリプト
```Makefile
gcd_euclid: gcd_euclid.o main_euclid.o
```
* `gcd_euclid.c` : 二つの整数から最大公約数を計算する関数`gcd_euclid`が定義されているCプログラム
* `main_euclid.c` : `main`関数が定義されているCプログラム
