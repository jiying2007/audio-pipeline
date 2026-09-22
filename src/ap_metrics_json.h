#ifndef AP_METRICS_JSON_H
#define AP_METRICS_JSON_H

#include <math.h>
#include <stdio.h>

/*
 * JSON has no NaN or infinity literals. Runtime metrics may legitimately carry
 * non-finite values while their accompanying validity flag is false, so encode
 * those values as JSON null instead of emitting implementation-specific
 * "nan"/"inf" tokens that strict parsers must reject.
 */
static inline int ap_metrics_json_write_number(FILE *stream, double value) {
    if (!stream) return 0;
    if (!isfinite(value)) return fputs("null", stream) >= 0;
    return fprintf(stream, "%.7g", value) >= 0;
}

#endif
