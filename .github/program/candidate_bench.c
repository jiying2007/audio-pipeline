#define _POSIX_C_SOURCE 200809L
#include "candidate_pipeline_inject.h"
#define ap_pipeline_init ap_candidate_pipeline_init
#include "../../bench/bench_pipeline.c"
