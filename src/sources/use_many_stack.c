#include <stdio.h>

volatile int aplusb(int a, int b) {
    if (b == 0) return a;
    return aplusb(a + 1, b - 1);
}

int main() {
    printf("%d\n", aplusb(0, 10000000));
}
