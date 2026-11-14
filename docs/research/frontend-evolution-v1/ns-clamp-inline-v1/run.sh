#!/bin/sh
set -eu
for mode in EMA MCRA; do
 gcc -std=c11 -O2 -ffp-contract=off -Wall -Wextra -Werror -DAP_BUILD_NS_$mode=1 -Isrc baseline.c candidate.c src/dsp/ap_fft.c harness.c -lm -o compare-$mode
 timeout 80 ./compare-$mode > result-$mode.txt 2>error-$mode.txt
 echo $? > exit-$mode.txt
done
