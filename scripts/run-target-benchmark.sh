#!/bin/sh
set -eu

BIN=${1:-./build/ap_bench}
SECONDS=${2:-120}
MAX_RTF=${3:-0.40}
MAX_P99_US=${4:-9000}
DSP_CPU=${5:-1}

if [ ! -x "$BIN" ]; then
    echo "benchmark binary is not executable: $BIN" >&2
    exit 2
fi

echo "=== audio-pipeline target benchmark ==="
echo "date=$(date -Iseconds 2>/dev/null || date)"
echo "uname=$(uname -a)"
echo "binary=$BIN seconds=$SECONDS max_rtf=$MAX_RTF max_p99_us=$MAX_P99_US dsp_cpu=$DSP_CPU"

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

CMD="$BIN $SECONDS $MAX_RTF $MAX_P99_US"
if command -v taskset >/dev/null 2>&1; then
    CMD="taskset -c $DSP_CPU $CMD"
fi

echo "--- benchmark ---"
echo "+ $CMD"

# /usr/bin/time is optional on small root filesystems. When present it adds
# max RSS, CPU percentage and scheduler counters without changing the DSP code.
if [ -x /usr/bin/time ]; then
    # shellcheck disable=SC2086
    /usr/bin/time -v sh -c "$CMD"
else
    sh -c "$CMD"
fi

echo "--- post-run memory ---"
if [ -r /proc/meminfo ]; then
    grep -E '^(MemTotal|MemFree|MemAvailable):' /proc/meminfo 2>/dev/null || true
fi

echo "PASS: target benchmark gates satisfied"
