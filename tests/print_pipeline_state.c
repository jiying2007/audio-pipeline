#include "audio_pipeline/audio_pipeline.h"
#include <stdio.h>

int main(void) {
    printf("%zu\n", ap_pipeline_state_size());
    return 0;
}
