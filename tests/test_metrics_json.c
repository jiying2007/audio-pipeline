#include "../src/ap_metrics_json.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    static const char expected[] =
        "{\"finite\":0.125,\"nan\":null,\"pos_inf\":null,\"neg_inf\":null}\n";
    char buffer[sizeof(expected) + 16];
    FILE *stream = tmpfile();
    size_t count;

    if (!stream) return 1;
    if (fputs("{\"finite\":", stream) < 0 ||
        !ap_metrics_json_write_number(stream, 0.125) ||
        fputs(",\"nan\":", stream) < 0 ||
        !ap_metrics_json_write_number(stream, NAN) ||
        fputs(",\"pos_inf\":", stream) < 0 ||
        !ap_metrics_json_write_number(stream, INFINITY) ||
        fputs(",\"neg_inf\":", stream) < 0 ||
        !ap_metrics_json_write_number(stream, -INFINITY) ||
        fputs("}\n", stream) < 0) {
        fclose(stream);
        return 2;
    }
    if (fflush(stream) != 0 || fseek(stream, 0, SEEK_SET) != 0) {
        fclose(stream);
        return 3;
    }
    count = fread(buffer, 1, sizeof(buffer) - 1, stream);
    fclose(stream);
    buffer[count] = '\0';
    return strcmp(buffer, expected) == 0 ? 0 : 4;
}
