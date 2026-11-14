#!/bin/sh
set -eu
for mode in EMA MCRA; do
 for arm in baseline candidate; do
  gcc -std=c11 -O2 -ffp-contract=off -Wall -Wextra -Werror -DAP_BUILD_NS_$mode=1 -DAP_BUILD_STAGE_NS=1 -DAP_BUILD_STAGE_RES=1 -Isrc -Iintegration/generated integration/$arm-unity.c integration/ns-harness.c -lm -o integration/$arm-$mode
  timeout 60 integration/$arm-$mode integration/$arm-$mode.bin > integration/$arm-$mode.txt
  gcc -std=c11 -O2 -ffp-contract=off -DAP_BUILD_NS_$mode=1 -DAP_BUILD_STAGE_NS=1 -DAP_BUILD_STAGE_RES=1 -Isrc -Iintegration/generated -c integration/$arm-unity.c -o integration/$arm-$mode.o
  objdump -d integration/$arm-$mode.o > integration/$arm-$mode.asm
 done
 cmp integration/baseline-$mode.bin integration/candidate-$mode.bin
 echo "$mode NS output/state/results BYTE_IDENTICAL"
done
