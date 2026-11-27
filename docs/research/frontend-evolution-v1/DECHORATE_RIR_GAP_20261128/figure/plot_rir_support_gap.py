#!/usr/bin/env python3
"""Plot the sealed 22-row JSON only: no RIR read, metric call, or DSP execution."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator


HERE = Path(__file__).resolve().parent
RESULT = HERE.parent / 'result.json'
EXPECTED = '1c2bfa4ae417c76c37f0b14851b72e541bff447e08129addae0ed67c72ba29c2'
STATE_ORDER = ['000000', '000001', '000010', '000100', '001000', '010000',
               '011000', '011100', '011110', '011111', '020002']
raw = RESULT.read_bytes()
assert hashlib.sha256(raw).hexdigest() == EXPECTED
result = json.loads(raw)
measurement = result['measurement']
assert measurement['physical_room_count'] == 1
assert measurement['scored_ir_count'] == 22
assert measurement['support_bound']['native_window_samples'] == 1677
assert measurement['support_bound']['sample_rate_hz'] == 48000
assert measurement['decision'] == 'DESCRIPTIVE_ONLY_NO_PROMOTION_NO_MODEL_FIT'
rows = measurement['cases']
expected_keys = [(state, mic) for state in STATE_ORDER for mic in (0, 1)]
assert [(row['room_state'], row['mic_index_zero_based']) for row in rows] == expected_keys
plot_data = json.loads((HERE / 'plot-data.json').read_text())
assert plot_data['source_result_sha256'] == EXPECTED
assert [(c['room_state'], c['mic_index_zero_based']) for c in plot_data['cases']] == expected_keys
for row, shown in zip(rows, plot_data['cases']):
    assert shown['source_fraction'] == row['uncovered_energy_fraction_lower_bound']
    assert shown['display_percent'] == 100.0 * row['uncovered_energy_fraction_lower_bound']

plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': 10,
    'axes.titlesize': 17,
    'axes.labelsize': 11,
    'axes.edgecolor': '#8a96a1',
    'axes.spines.top': False,
    'axes.spines.right': False,
    'svg.hashsalt': EXPECTED,
})
fig, ax = plt.subplots(figsize=(13.2, 7.4))
fig.subplots_adjust(left=0.085, right=0.985, top=0.80, bottom=0.23)
fig.text(0.085, 0.945, 'Measured RIR energy beyond a fixed support window',
         ha='left', va='top', fontsize=19, fontweight='bold', color='#20303c')
fig.text(0.085, 0.890, '1 physical room  |  11 dependent states  |  22 correlated views  |  Descriptive only',
         ha='left', va='top', fontsize=11, color='#425564')
fig.text(0.085, 0.853, 'Oracle window: 1,677 samples / 48 kHz = 34.9375 ms; fixed c = 343 m/s model family',
         ha='left', va='top', fontsize=10.5, color='#425564')
width = 0.35
for mic, color in ((0, '#286f9b'), (1, '#d88a3c')):
    values = [100.0 * row['uncovered_energy_fraction_lower_bound']
              for row in rows if row['mic_index_zero_based'] == mic]
    positions = [i + (-width/2 if mic == 0 else width/2) for i in range(len(STATE_ORDER))]
    bars = ax.bar(positions, values, width=width, label='Mic %d (zero-based)' % mic,
                  color=color, zorder=3)
    ax.bar_label(bars, labels=['%.2f' % value for value in values], padding=3,
                 fontsize=8.0, color='#243641')
ax.set_xticks(list(range(len(STATE_ORDER))), labels=STATE_ORDER)
ax.tick_params(axis='x', length=0, labelsize=9.5, pad=8)
ax.set_xlim(-0.65, len(STATE_ORDER)-0.35)
ax.set_ylim(0, 37)
ax.yaxis.set_major_locator(MultipleLocator(5))
ax.set_ylabel('Uncovered finite-record energy lower bound (%)', labelpad=11)
ax.set_xlabel('Frozen file-name state token (one shared room)', labelpad=15)
ax.grid(axis='y', color='#dfe5e9', linewidth=0.7, zorder=0)
ax.legend(loc='upper left', frameon=False, ncol=2, fontsize=10)
fig.text(0.085, 0.116,
         'U = 1 - max window energy / total original-record energy. Only the overall window position is optimized.',
         ha='left', fontsize=10, color='#425564')
fig.text(0.085, 0.083,
         'Not full model-fit error or a pure-room-reverberation share. No candidate fitting, ranking, or promotion.',
         ha='left', fontsize=10, color='#425564')
fig.text(0.085, 0.040,
         'Source: FE-SIM-RIR-SUPPORT-GAP-V1  |  a058b0258296  |  result SHA256: ' + EXPECTED[:20] + '...',
         ha='left', fontsize=8.5, color='#62727e')
fig.savefig(HERE / 'rir-support-gap.png', dpi=240,
            metadata={'Description': 'Data-only descriptive scientific plot; result SHA256 ' + EXPECTED})
fig.savefig(HERE / 'rir-support-gap.svg',
            metadata={'Date': None, 'Description': 'Data-only descriptive scientific plot; result SHA256 ' + EXPECTED})
svg_path = HERE / 'rir-support-gap.svg'
# Matplotlib emits trailing spaces in path data; keep the public text artifact clean.
svg_path.write_text('\n'.join(line.rstrip() for line in svg_path.read_text().splitlines()) + '\n')
plt.close(fig)
print(json.dumps({'status': 'PLOTTED_SEALED_JSON_ONLY', 'matplotlib': matplotlib.__version__,
                  'result_sha256': EXPECTED, 'data_rows': 22,
                  'IR_samples_read': False, 'new_DSP_executions': 0,
                  'files': ['rir-support-gap.png', 'rir-support-gap.svg']}, sort_keys=True))
