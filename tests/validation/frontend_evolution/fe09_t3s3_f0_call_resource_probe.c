/* Finite measurement only. Original B3 driver and DSP bytes are unchanged. */
#define _POSIX_C_SOURCE 200809L
#define main fe_t3s3_original_driver_main
#include "fe09_b3_f0_composition_test.c"
#undef main
#include <time.h>

typedef struct {
    uint64_t cpu_ns, wall_ns;
    uint32_t calls;
    int32_t status;
} resource_sample;
typedef struct { uint64_t cpu_ns, wall_ns; } resource_stamp;
static resource_sample resource_frames[FE_B3_F0_FRAMES][3];
static resource_sample resource_bind;
static uint32_t resource_events[FE_B3_F0_FRAMES];
static uint32_t resource_failed;
static uint64_t cpu_resolution_ns, wall_resolution_ns;

static uint64_t resource_ns(const struct timespec *value) {
    if (value->tv_sec < 0 || value->tv_nsec < 0 || value->tv_nsec >= 1000000000L ||
        (uint64_t)value->tv_sec > UINT64_MAX / UINT64_C(1000000000)) {
        resource_failed = 1u;
        return 0u;
    }
    return (uint64_t)value->tv_sec * UINT64_C(1000000000) + (uint64_t)value->tv_nsec;
}
static resource_stamp resource_begin(void) {
    struct timespec cpu = {0,0}, wall = {0,0};
    resource_stamp stamp;
    if (clock_gettime(CLOCK_MONOTONIC,&wall) != 0 ||
        clock_gettime(CLOCK_THREAD_CPUTIME_ID,&cpu) != 0) resource_failed = 1u;
    stamp.wall_ns = resource_ns(&wall); stamp.cpu_ns = resource_ns(&cpu);
    return stamp;
}
static void resource_end(resource_sample *sample, resource_stamp start, int status) {
    struct timespec cpu = {0,0}, wall = {0,0};
    uint64_t end_cpu, end_wall;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID,&cpu) != 0 ||
        clock_gettime(CLOCK_MONOTONIC,&wall) != 0) resource_failed = 1u;
    end_cpu = resource_ns(&cpu); end_wall = resource_ns(&wall);
    if (end_cpu < start.cpu_ns || end_wall < start.wall_ns || sample->calls) {
        resource_failed = 1u;
        return;
    }
    sample->cpu_ns = end_cpu - start.cpu_ns;
    sample->wall_ns = end_wall - start.wall_ns;
    sample->calls = 1u; sample->status = status;
}
static resource_sample *resource_slot(uint64_t sequence, unsigned column) {
    if (!sequence || sequence > FE_B3_F0_FRAMES || column > 2u ||
        sequence != (uint64_t)attempted_frame) {
        resource_failed = 1u;
        return NULL;
    }
    return &resource_frames[sequence - 1u][column];
}

fe_b3_f0_status __real_fe_b3_f0_bind(fe_b3_f0 *, fe_b1s0_state *, ap_pipeline_t *, size_t);
fe_b3_f0_status __wrap_fe_b3_f0_bind(fe_b3_f0 *b, fe_b1s0_state *q,
                                    ap_pipeline_t *p, size_t bytes) {
    resource_stamp stamp = resource_begin();
    fe_b3_f0_status status = __real_fe_b3_f0_bind(b,q,p,bytes);
    resource_end(&resource_bind,stamp,(int)status);
    return status;
}
fe_b3_f0_status __real_fe_b3_f0_process_one(fe_b3_f0 *, int16_t *, size_t,
                                          void *, size_t, fe_b3_f0_receipt *);
fe_b3_f0_status __wrap_fe_b3_f0_process_one(fe_b3_f0 *b, int16_t *out, size_t count,
        void *work, size_t bytes, fe_b3_f0_receipt *receipt) {
    resource_sample *slot = resource_slot(b->accepted + 1u,2u);
    resource_stamp stamp = resource_begin();
    fe_b3_f0_status status = __real_fe_b3_f0_process_one(b,out,count,work,bytes,receipt);
    if (slot) resource_end(slot,stamp,(int)status);
    return status;
}
fe_b1s0_status __real_fe_b1s0_capture_submit(fe_b1s0_state *, uint32_t, uint64_t,
                                           uint64_t, const int16_t *, size_t);
fe_b1s0_status __wrap_fe_b1s0_capture_submit(fe_b1s0_state *q, uint32_t id,
        uint64_t generation, uint64_t sequence, const int16_t *pcm, size_t count) {
    resource_sample *slot = resource_slot(sequence,0u);
    resource_stamp stamp = resource_begin();
    fe_b1s0_status status = __real_fe_b1s0_capture_submit(q,id,generation,sequence,pcm,count);
    if (slot) resource_end(slot,stamp,(int)status);
    return status;
}
fe_b1s0_status __real_fe_b1s0_render_present(fe_b1s0_state *, uint32_t, uint64_t,
                            uint64_t, uint32_t, uint32_t, const int16_t *, size_t);
fe_b1s0_status __wrap_fe_b1s0_render_present(fe_b1s0_state *q, uint32_t id,
        uint64_t generation, uint64_t sequence, uint32_t epoch, uint32_t gap,
        const int16_t *pcm, size_t count) {
    resource_sample *slot = resource_slot(sequence,1u);
    resource_stamp stamp = resource_begin();
    fe_b1s0_status status = __real_fe_b1s0_render_present(q,id,generation,sequence,
                                                       epoch,gap,pcm,count);
    if (slot) {
        resource_end(slot,stamp,(int)status);
        resource_events[sequence - 1u] = 1u;
    }
    return status;
}
fe_b1s0_status __real_fe_b1s0_render_absent(fe_b1s0_state *, uint32_t, uint64_t,
                                         uint64_t, uint32_t, uint32_t);
fe_b1s0_status __wrap_fe_b1s0_render_absent(fe_b1s0_state *q, uint32_t id,
        uint64_t generation, uint64_t sequence, uint32_t epoch, uint32_t reason) {
    resource_sample *slot = resource_slot(sequence,1u);
    resource_stamp stamp = resource_begin();
    fe_b1s0_status status = __real_fe_b1s0_render_absent(q,id,generation,sequence,epoch,reason);
    if (slot) {
        resource_end(slot,stamp,(int)status);
        resource_events[sequence - 1u] = 2u;
    }
    return status;
}

static void resource_sample_json(FILE *f,const resource_sample *sample) {
    fprintf(f,"{\"cpu_ns\":%" PRIu64 ",\"wall_ns\":%" PRIu64
              ",\"calls\":%u,\"status\":%" PRId32 "}",
            sample->cpu_ns,sample->wall_ns,sample->calls,sample->status);
}
int main(int argc, char **argv) {
    struct timespec cpu = {0,0},wall = {0,0};
    const char *dir = NULL;
    FILE *f;
    int result;
    /* This probe accepts only the two registered plain, complete trajectories. */
    if (argc != 11 || strcmp(argv[1],"--case") ||
        (strcmp(argv[2],"ALL_P") && strcmp(argv[2],"PAP")) ||
        strcmp(argv[3],"--mode") || strcmp(argv[4],"adapter") ||
        strcmp(argv[5],"--future") || strcmp(argv[6],"0") ||
        strcmp(argv[7],"--negatives") || strcmp(argv[8],"0") ||
        strcmp(argv[9],"--output")) return 2;
    dir = argv[10];
    if (clock_getres(CLOCK_THREAD_CPUTIME_ID,&cpu) != 0 ||
        clock_getres(CLOCK_MONOTONIC,&wall) != 0) resource_failed = 1u;
    cpu_resolution_ns = resource_ns(&cpu); wall_resolution_ns = resource_ns(&wall);
    result = fe_t3s3_original_driver_main(argc,argv);
    if (completed != FE_B3_F0_FRAMES || resource_bind.calls != 1u ||
        resource_bind.status != 0 || !cpu_resolution_ns || !wall_resolution_ns)
        resource_failed = 1u;
    for (unsigned i=0;i<FE_B3_F0_FRAMES;++i) {
        unsigned event=(unsigned)(case_pap && i>=200u && i<240u)?2u:1u;
        if (resource_events[i] != event) resource_failed = 1u;
        for (unsigned j=0;j<3u;++j)
            if (resource_frames[i][j].calls != 1u || resource_frames[i][j].status != 0)
                resource_failed = 1u;
    }
    f = b3_test_file(dir,"timing.json");
    if (!f) return 2;
    fprintf(f,"{\"schema_version\":1,\"id\":\"FE09-T3S3-F0-ACTUAL-CALL-RESOURCE-V1\","
          "\"case\":\"%s\",\"failed\":%u,\"completed_frames\":%u,"
          "\"clock_cpu\":\"CLOCK_THREAD_CPUTIME_ID\",\"clock_wall\":\"CLOCK_MONOTONIC\","
          "\"cpu_resolution_ns\":%" PRIu64 ",\"wall_resolution_ns\":%" PRIu64
          ",\"timing_storage_bytes\":%zu,\"bind\":",
          case_pap?"PAP":"ALL_P",resource_failed,completed,cpu_resolution_ns,
          wall_resolution_ns,sizeof(resource_frames)+sizeof(resource_events)+sizeof(resource_bind)+
          sizeof(resource_failed)+sizeof(cpu_resolution_ns)+sizeof(wall_resolution_ns));
    resource_sample_json(f,&resource_bind);
    fputs(",\"frames\":[",f);
    for (unsigned i=0;i<FE_B3_F0_FRAMES;++i) {
        fprintf(f,"%s{\"seq\":%u,\"event\":%u,\"capture\":",i?",":"",i+1u,resource_events[i]);
        resource_sample_json(f,&resource_frames[i][0]);fputs(",\"render\":",f);
        resource_sample_json(f,&resource_frames[i][1]);fputs(",\"worker\":",f);
        resource_sample_json(f,&resource_frames[i][2]);fputc('}',f);
    }
    fputs("]}\n",f);
    if (fclose(f) != 0 || resource_failed || result) return 2;
    return 0;
}
