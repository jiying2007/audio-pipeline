#!/bin/sh
set -eu

BIN=${1:-./build/ap_runtime_bench}
SECONDS=${2:-28800}
MAX_OVERRUNS=${3:-0}
MIN_FULL_RATIO=${4:-0.999}
DSP_CPU=${5:-1}

if [ ! -x "$BIN" ]; then
    echo "runtime benchmark binary is not executable: $BIN" >&2
    exit 2
fi

echo "=== audio-pipeline target runtime soak ==="
echo "date=$(date -Iseconds 2>/dev/null || date)"
echo "uname=$(uname -a)"
echo "binary=$BIN seconds=$SECONDS max_overruns=$MAX_OVERRUNS min_full_ratio=$MIN_FULL_RATIO dsp_cpu=$DSP_CPU"

if [ -r /proc/cpuinfo ]; then
    echo "--- /proc/cpuinfo summary ---"
    grep -E '^(processor|model name|CPU architecture|Hardware|BogoMIPS)' /proc/cpuinfo 2>/dev/null || true
fi

for f in \
    /sys/devices/system/cpu/cpu${DSP_CPU}/cpufreq/scaling_governor \
    /sys/devices/system/cpu/cpu${DSP_CPU}/cpufreq/scaling_cur_freq \
    /sys/devices/system/cpu/cpu${DSP_CPU}/cpufreq/cpuinfo_max_freq; do
    if [ -r "$f" ]; then
        echo "$(basename "$f")=$(cat "$f")"
    fi
done

CMD="$BIN $SECONDS $MAX_OVERRUNS $MIN_FULL_RATIO $DSP_CPU"
echo "--- runtime soak ---"
echo "+ $CMD"

if [ -x /usr/bin/time ]; then
    /usr/bin/time -v sh -c "$CMD"
else
    sh -c "$CMD"
fi

echo "PASS: runtime soak gates satisfied"
