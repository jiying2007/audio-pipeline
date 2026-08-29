#!/usr/bin/env python3
from pathlib import Path
import re
p = Path('src/platform/linux/ap_runtime.c')
s = p.read_text(encoding='utf-8')

# Rare fault/diagnostic counters are intentionally 32-bit saturating internally.
# Public metrics_v3 widens them to uint64_t. Keep high-rate/lifetime frame counters
# on the existing split 64-bit implementation.
for name in ('failed_frames','render_push_failures','capture_process_failures','observed_cpu_changes','critical_events'):
    old = f'    ap_counter64_t {name};'
    new = f'    atomic_uint {name};'
    if old not in s: raise SystemExit(f'missing struct counter {name}')
    s = s.replace(old, new, 1)

anchor = '''static void update_max(atomic_uint *dst, uint32_t value) {\n    unsigned current = atomic_load_explicit(dst, memory_order_relaxed);\n    while (value > current &&\n           !atomic_compare_exchange_weak_explicit(dst,\n                                                  &current,\n                                                  value,\n                                                  memory_order_relaxed,\n                                                  memory_order_relaxed)) {\n    }\n}\n'''
helper = anchor + '''\nstatic void counter32_inc_sat(atomic_uint *counter) {\n    unsigned current = atomic_load_explicit(counter, memory_order_relaxed);\n    while (current != UINT32_MAX &&\n           !atomic_compare_exchange_weak_explicit(counter,\n                                                  &current,\n                                                  current + 1u,\n                                                  memory_order_relaxed,\n                                                  memory_order_relaxed)) {\n    }\n}\n'''
if anchor not in s: raise SystemExit('update_max anchor missing')
s = s.replace(anchor, helper, 1)

# Initialization.
for name in ('failed_frames','render_push_failures','capture_process_failures','observed_cpu_changes','critical_events'):
    old = f'    counter64_init(&runtime->{name});'
    new = f'    atomic_init(&runtime->{name}, 0u);'
    if old not in s: raise SystemExit(f'missing init {name}')
    s = s.replace(old, new, 1)

# All additions for these counters are increments by one in current implementation.
for name in ('failed_frames','render_push_failures','capture_process_failures','observed_cpu_changes','critical_events'):
    old = f'counter64_add(&runtime->{name}, 1u)'
    if old not in s: raise SystemExit(f'missing increment {name}')
    s = s.replace(old, f'counter32_inc_sat(&runtime->{name})')

# Widen rare counters on public read.
for name in ('failed_frames','render_push_failures','capture_process_failures','observed_cpu_changes','critical_events'):
    old = f'counter64_read(&runtime->{name})'
    if old not in s: raise SystemExit(f'missing read {name}')
    s = s.replace(old, f'(uint64_t)atomic_load_explicit(&runtime->{name}, memory_order_acquire)')

# GCC correctly points out the continue path in the seqlock loop can bypass writes.
s = s.replace('''    unsigned seq0, seq1;\n    unsigned lo, hi;\n''', '''    unsigned seq0 = 0u;\n    unsigned seq1 = 0u;\n    unsigned lo = 0u;\n    unsigned hi = 0u;\n''', 1)

p.write_text(s.rstrip() + '\n', encoding='utf-8')
print('runtime v1.2 rare-counter compaction and seqlock warning fix applied')
