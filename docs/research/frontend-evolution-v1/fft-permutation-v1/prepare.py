from pathlib import Path
p=Path(__file__).parent
src=(p/'src/dsp/ap_fft.c').read_text()
(p/'baseline.c').write_text(src.replace('ap_fft(', 'baseline_fft(').replace('ap_clampf(', 'baseline_clampf(').replace('ap_rms_dbfs(', 'baseline_rms_dbfs('))
start=src.index('    for (i = 1u, j = 0u; i < n; ++i) {',src.index('void ap_fft('))
end=src.index('\n\n    if (n <= AP_FFT_TWIDDLE_N',start)
old=src[start:end]
new='''    if (n > 0u && n <= 512u && (n & (n - 1u)) == 0u) {
        uint32_t shift = 0u, size = n;
        while (size < 512u) { ++shift; size <<= 1u; }
        for (i = 1u; i < n; ++i) {
            j = AP_FFT_BITREV9[i] >> shift;
            if (i < j) {
                ap_complex_t t = x[i]; x[i] = x[j]; x[j] = t;
            }
        }
    } else {
'''+old+'''\n    }'''
vals=[int(f'{i:09b}'[::-1],2) for i in range(512)]
table='static const uint16_t AP_FFT_BITREV9[512] = {\n'+',\n'.join('    '+', '.join(str(v)+'u' for v in vals[k:k+16]) for k in range(0,512,16))+'\n};\n\n'
src=src[:start]+new+src[end:]
src=src.replace('void ap_fft(',table+'void ap_fft(')
(p/'candidate.c').write_text(src.replace('ap_fft(', 'candidate_fft(').replace('ap_clampf(', 'candidate_clampf(').replace('ap_rms_dbfs(', 'candidate_rms_dbfs('))
(p/'candidate-production.c').write_text(src)
