#include "audio_pipeline/audio_runtime.h"
#include <stdio.h>

int main(void) {
    printf("%zu\n", ap_runtime_state_size());
    return 0;
}
