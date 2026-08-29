#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_runtime.h"
#include <stddef.h>
#include <stdio.h>
int main(void) {
    printf("ap_config_t=%zu\n", sizeof(ap_config_t));
    printf("ap_config_t.stages=%zu\n", offsetof(ap_config_t, stages));
    printf("ap_metrics_t=%zu\n", sizeof(ap_metrics_t));
    printf("ap_metrics_t.processed_frames=%zu\n", offsetof(ap_metrics_t, processed_frames));
    printf("ap_runtime_config_t=%zu\n", sizeof(ap_runtime_config_t));
    printf("ap_runtime_metrics_t=%zu\n", sizeof(ap_runtime_metrics_t));
    printf("AP_OK=%d\n", (int)AP_OK);
    printf("AP_EINVAL=%d\n", (int)AP_EINVAL);
    printf("AP_EFULL=%d\n", (int)AP_EFULL);
    printf("AP_EEMPTY=%d\n", (int)AP_EEMPTY);
    return 0;
}
