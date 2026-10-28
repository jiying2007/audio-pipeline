/* Exercise exact, legal scheduling boundaries in the runtime's SPSC/atomic
 * protocols. Only this test translation unit wraps atomics; installed runtime
 * code has no test hooks or additional public interfaces. The wrappers retain
 * the original C11 operation and its memory order before yielding to a peer.
 */
#define _GNU_SOURCE
#include "audio_pipeline/audio_runtime.h"
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>

static void after_atomic_store(const volatile void *object);
static void after_atomic_load(const volatile void *object);

static void test_store_uint(volatile atomic_uint *object, unsigned value,
                            memory_order order) {
    atomic_store_explicit(object, value, order);
    after_atomic_store(object);
}

static void test_store_int(volatile atomic_int *object, int value,
                           memory_order order) {
    atomic_store_explicit(object, value, order);
    after_atomic_store(object);
}

static unsigned test_load_uint(const volatile atomic_uint *object,
                                memory_order order) {
    const unsigned value = atomic_load_explicit(object, order);
    after_atomic_load(object);
    return value;
}

static int test_load_int(const volatile atomic_int *object, memory_order order) {
    const int value = atomic_load_explicit(object, order);
    after_atomic_load(object);
    return value;
}

#undef atomic_store_explicit
#define atomic_store_explicit(object, value, order) \
    _Generic((object), \
             atomic_uint *: test_store_uint, \
             volatile atomic_uint *: test_store_uint, \
             atomic_int *: test_store_int, \
             volatile atomic_int *: test_store_int)((object), (value), (order))

#undef atomic_load_explicit
#define atomic_load_explicit(object, order) \
    _Generic((object), \
             atomic_uint *: test_load_uint, \
             const atomic_uint *: test_load_uint, \
             volatile atomic_uint *: test_load_uint, \
             const volatile atomic_uint *: test_load_uint, \
             atomic_int *: test_load_int, \
             const atomic_int *: test_load_int, \
             volatile atomic_int *: test_load_int, \
             const volatile atomic_int *: test_load_int)((object), (order))

static int test_pthread_join(pthread_t thread, void **result);
static ap_status_t test_pipeline_get_tuning(const ap_pipeline_t *pipeline,
                                           ap_tuning_t *tuning);
#define pthread_join test_pthread_join
#define ap_pipeline_get_tuning test_pipeline_get_tuning
#include "../src/platform/linux/ap_runtime.c"
#undef ap_pipeline_get_tuning
#undef pthread_join

static _Alignas(AP_RUNTIME_STATE_ALIGNMENT) ap_runtime_t runtime;
static _Alignas(AP_PIPELINE_STATE_ALIGNMENT)
unsigned char pipeline_memory[AP_PIPELINE_STATE_MAX_BYTES];
static const volatile void *store_watch;
static void (*store_peer)(void);
static void (*load_peer)(const volatile void *object);
static unsigned peer_calls;
static ap_status_t replacement_status;
static unsigned refill_remaining;
static void (*join_peer)(void);
static unsigned tuning_snapshot_calls;

static int test_pthread_join(pthread_t thread, void **result) {
    /* The peer runs after stop has requested exit but before join confirms
     * that the worker has released the pipeline. The real join still runs. */
    if (join_peer) join_peer();
    return pthread_join(thread, result);
}

static ap_status_t test_pipeline_get_tuning(const ap_pipeline_t *pipeline,
                                           ap_tuning_t *tuning) {
    tuning_snapshot_calls++;
    return ap_pipeline_get_tuning(pipeline, tuning);
}

static void after_atomic_store(const volatile void *object) {
    if (object == store_watch && store_peer) store_peer();
}

static void after_atomic_load(const volatile void *object) {
    if (load_peer) load_peer(object);
}

static void reuse_output_slot(void) {
    const unsigned head = atomic_load_explicit(&runtime.out_head, memory_order_relaxed);
    const unsigned tail = atomic_load_explicit(&runtime.out_tail, memory_order_acquire);
    ap_rt_output_t *slot = &runtime.out[head & AP_RT_MASK];
    assert(head - tail < AP_RT_DEPTH);
    slot->audio[0] = 999;
    memset(&slot->metrics, 0, sizeof(slot->metrics));
    slot->metrics.quality = AP_QUALITY_SAFE;
    slot->status = replacement_status;
    atomic_store_explicit(&runtime.out_head, head + 1u, memory_order_release);
    peer_calls++;
}

static void test_output_status_ownership(ap_status_t original_status,
                                         ap_status_t next_status) {
    int16_t output = 0;
    ap_metrics_t frame_metrics;
    ap_status_t status;
    memset(&runtime, 0, sizeof(runtime));
    init_runtime_atomics(&runtime);
    runtime.io_frames = 1u;
    runtime.out[0].audio[0] = 123;
    runtime.out[0].metrics.quality = AP_QUALITY_FULL;
    runtime.out[0].status = original_status;
    atomic_store_explicit(&runtime.out_head, AP_RT_DEPTH, memory_order_release);
    replacement_status = next_status;
    peer_calls = 0u;
    store_watch = &runtime.out_tail;
    store_peer = reuse_output_slot;

    status = ap_runtime_receive(&runtime, &output, &frame_metrics);

    store_peer = NULL;
    store_watch = NULL;
    assert(peer_calls == 1u);
    assert(output == 123);
    assert(frame_metrics.quality == AP_QUALITY_FULL);
    assert(status == original_status);
    assert(runtime.out[0].status == next_status);
}

static void refill_command_slot(void) {
    ap_runtime_command_t command = {0};
    peer_calls++;
    /* A finite peer budget also makes the broken implementation terminate, so
     * the regression fails an exact progress assertion instead of timing out. */
    if (!refill_remaining) return;
    refill_remaining--;
    command.struct_size = sizeof(command);
    command.api_version = AP_RUNTIME_API_VERSION;
    command.kind = AP_RUNTIME_COMMAND_RESET;
    assert(ap_runtime_command(&runtime, &command) == AP_OK);
}

static void test_command_boundary_budget(unsigned initial_tail) {
    ap_config_t pipeline_config = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t config = ap_runtime_config_default();
    ap_runtime_options_t options = ap_runtime_options_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *opened = NULL;
    ap_runtime_command_t command = {0};
    unsigned i;
    assert(ap_pipeline_init(pipeline_memory, sizeof(pipeline_memory),
                            &pipeline_config, &pipeline) == AP_OK);
    assert(ap_runtime_open(&runtime, sizeof(runtime), pipeline, &config,
                            &options, &opened) == AP_OK);
    assert(opened == &runtime);
    atomic_store_explicit(&runtime.command_head, initial_tail, memory_order_relaxed);
    atomic_store_explicit(&runtime.command_tail, initial_tail, memory_order_relaxed);
    command.struct_size = sizeof(command);
    command.api_version = AP_RUNTIME_API_VERSION;
    command.kind = AP_RUNTIME_COMMAND_RESET;
    for (i = 0u; i < AP_RUNTIME_COMMAND_QUEUE_DEPTH; ++i)
        assert(ap_runtime_command(&runtime, &command) == AP_OK);

    peer_calls = 0u;
    refill_remaining = 32u;
    store_watch = &runtime.command_tail;
    store_peer = refill_command_slot;
    runtime_drain_commands(&runtime);
    store_peer = NULL;
    store_watch = NULL;

    assert(peer_calls == AP_RUNTIME_COMMAND_QUEUE_DEPTH);
    assert(refill_remaining == 32u - AP_RUNTIME_COMMAND_QUEUE_DEPTH);
    assert(atomic_load(&runtime.command_tail) ==
           initial_tail + AP_RUNTIME_COMMAND_QUEUE_DEPTH);
    assert(atomic_load(&runtime.command_head) - atomic_load(&runtime.command_tail) ==
           AP_RUNTIME_COMMAND_QUEUE_DEPTH);
    runtime_drain_commands(&runtime);
    assert(atomic_load(&runtime.command_head) == atomic_load(&runtime.command_tail));
    ap_runtime_deinit(&runtime);
}

static void submit_tuning_before_join(void) {
    const unsigned snapshots = tuning_snapshot_calls;
    ap_runtime_command_t command = {0};
    command.struct_size = sizeof(command);
    command.api_version = AP_RUNTIME_API_VERSION;
    command.kind = AP_RUNTIME_COMMAND_SET_TUNING;
    command.data.tuning.struct_size = sizeof(command.data.tuning);
    command.data.tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
    command.data.tuning.mask = AP_TUNING_LIMITER;
    command.data.tuning.limiter_dbfs = -6.0f;
    assert(ap_runtime_command(&runtime, &command) == AP_OK);
    /* Admission must not inspect a pipeline whose owner has not joined. */
    assert(tuning_snapshot_calls == snapshots);
    assert(ap_runtime_start(&runtime) == AP_ESTATE);
    assert(ap_runtime_attach_flight_recorder(&runtime, NULL) == AP_ESTATE);
    peer_calls++;
}

static void test_stop_keeps_worker_ownership_until_join(void) {
    ap_config_t pipeline_config = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t config = ap_runtime_config_default();
    ap_runtime_options_t options = ap_runtime_options_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *opened = NULL;
    ap_tuning_t direct = {0};
    ap_runtime_command_t command = {0};
    unsigned snapshots;
    assert(ap_pipeline_init(pipeline_memory, sizeof(pipeline_memory),
                            &pipeline_config, &pipeline) == AP_OK);
    assert(ap_runtime_open(&runtime, sizeof(runtime), pipeline, &config,
                           &options, &opened) == AP_OK);
    assert(ap_runtime_start(&runtime) == AP_OK);
    peer_calls = 0u;
    join_peer = submit_tuning_before_join;
    ap_runtime_stop(&runtime);
    join_peer = NULL;
    assert(peer_calls == 1u);

    /* A completed stop does hand ownership back: a direct caller change must
     * still be included when the next queued tuning is admitted. */
    direct.struct_size = sizeof(direct);
    direct.api_version = AP_PIPELINE_CONTROL_API_VERSION;
    direct.mask = AP_TUNING_AGC_TARGET;
    direct.agc_target_dbfs = -24.0f;
    assert(ap_pipeline_apply_tuning(pipeline, &direct) == AP_OK);
    snapshots = tuning_snapshot_calls;
    command.struct_size = sizeof(command);
    command.api_version = AP_RUNTIME_API_VERSION;
    command.kind = AP_RUNTIME_COMMAND_SET_TUNING;
    command.data.tuning.struct_size = sizeof(command.data.tuning);
    command.data.tuning.api_version = AP_PIPELINE_CONTROL_API_VERSION;
    command.data.tuning.mask = AP_TUNING_LIMITER;
    command.data.tuning.limiter_dbfs = -20.0f;
    assert(ap_runtime_command(&runtime, &command) == AP_OK);
    assert(tuning_snapshot_calls == snapshots + 1u);
    ap_runtime_deinit(&runtime);
}

/* Pause the real writer after its last payload store but before its even
 * sequence publication. All scheduling state is protected by the mutex; hook
 * pointers and watched objects remain fixed until the writer has joined. */
static struct {
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    pthread_t reader;
    unsigned start;
    unsigned paused;
    unsigned release;
    unsigned done;
} snapshot_schedule;
static const atomic_uint *snapshot_seq;
static const atomic_uint *snapshot_low;
static ap_counter64_t *snapshot_counter;
static unsigned snapshot_sequence_reads;
static unsigned snapshot_started;

static void pause_snapshot_writer(void) {
    assert(pthread_mutex_lock(&snapshot_schedule.mutex) == 0);
    snapshot_schedule.paused = 1u;
    assert(pthread_cond_broadcast(&snapshot_schedule.cond) == 0);
    while (!snapshot_schedule.release)
        assert(pthread_cond_wait(&snapshot_schedule.cond, &snapshot_schedule.mutex) == 0);
    assert(pthread_mutex_unlock(&snapshot_schedule.mutex) == 0);
}

static void *write_snapshot(void *unused) {
    (void)unused;
    assert(pthread_mutex_lock(&snapshot_schedule.mutex) == 0);
    while (!snapshot_schedule.start)
        assert(pthread_cond_wait(&snapshot_schedule.cond, &snapshot_schedule.mutex) == 0);
    assert(pthread_mutex_unlock(&snapshot_schedule.mutex) == 0);
    if (snapshot_counter) {
        counter64_add(snapshot_counter, 1u);
    } else {
        runtime.worker_sequence = (UINT64_C(1) << 32u) | 222u;
        runtime_latch_critical(&runtime, AP_EVENT_PIPELINE_ERROR,
                               AP_EVENT_FATAL, 222, -333);
    }
    assert(pthread_mutex_lock(&snapshot_schedule.mutex) == 0);
    snapshot_schedule.done = 1u;
    assert(pthread_cond_broadcast(&snapshot_schedule.cond) == 0);
    assert(pthread_mutex_unlock(&snapshot_schedule.mutex) == 0);
    return NULL;
}

static void start_snapshot_writer(void) {
    snapshot_started = 1u;
    assert(pthread_mutex_lock(&snapshot_schedule.mutex) == 0);
    snapshot_schedule.start = 1u;
    assert(pthread_cond_broadcast(&snapshot_schedule.cond) == 0);
    while (!snapshot_schedule.paused)
        assert(pthread_cond_wait(&snapshot_schedule.cond, &snapshot_schedule.mutex) == 0);
    assert(pthread_mutex_unlock(&snapshot_schedule.mutex) == 0);
}

static void finish_snapshot_writer(void) {
    assert(pthread_mutex_lock(&snapshot_schedule.mutex) == 0);
    snapshot_schedule.release = 1u;
    assert(pthread_cond_broadcast(&snapshot_schedule.cond) == 0);
    while (!snapshot_schedule.done)
        assert(pthread_cond_wait(&snapshot_schedule.cond, &snapshot_schedule.mutex) == 0);
    assert(pthread_mutex_unlock(&snapshot_schedule.mutex) == 0);
}

static void interleave_snapshot_read(const volatile void *object) {
    if (!pthread_equal(pthread_self(), snapshot_schedule.reader)) return;
    if (object == snapshot_low && !snapshot_started) start_snapshot_writer();
    if (object == snapshot_seq) {
        snapshot_sequence_reads++;
        /* begin-even, end-odd, begin-odd must not accept a partial snapshot.
         * Keep the writer paused through that third load. On the fourth, let
         * it commit; the cached odd load still requires one further retry. */
        if (snapshot_sequence_reads == 4u) finish_snapshot_writer();
    }
}

static pthread_t setup_snapshot_schedule(void) {
    pthread_t writer;
    memset(&snapshot_schedule, 0, sizeof(snapshot_schedule));
    assert(pthread_mutex_init(&snapshot_schedule.mutex, NULL) == 0);
    assert(pthread_cond_init(&snapshot_schedule.cond, NULL) == 0);
    snapshot_schedule.reader = pthread_self();
    snapshot_sequence_reads = 0u;
    snapshot_started = 0u;
    store_peer = pause_snapshot_writer;
    load_peer = interleave_snapshot_read;
    assert(pthread_create(&writer, NULL, write_snapshot, NULL) == 0);
    return writer;
}

static void teardown_snapshot_schedule(pthread_t writer) {
    /* Also unblock a writer when the old, broken reader returns too early. */
    finish_snapshot_writer();
    assert(pthread_join(writer, NULL) == 0);
    load_peer = NULL;
    store_peer = NULL;
    store_watch = NULL;
    assert(pthread_cond_destroy(&snapshot_schedule.cond) == 0);
    assert(pthread_mutex_destroy(&snapshot_schedule.mutex) == 0);
}

static void test_critical_snapshot(unsigned initial_seq, unsigned initially_odd) {
    ap_runtime_critical_state_t state = {0};
    pthread_t writer;
    memset(&runtime, 0, sizeof(runtime));
    init_runtime_atomics(&runtime);
    runtime.worker_sequence = 111u;
    runtime_latch_critical(&runtime, AP_EVENT_DSP_DEADLINE_MISS, AP_EVENT_ERROR, 111, 0);
    atomic_store_explicit(&runtime.critical_seq, initial_seq, memory_order_relaxed);
    snapshot_seq = &runtime.critical_seq;
    snapshot_low = &runtime.critical_frame_lo;
    snapshot_counter = NULL;
    store_watch = &runtime.critical_arg1;
    writer = setup_snapshot_schedule();
    if (initially_odd) start_snapshot_writer();
    state.struct_size = sizeof(state);
    state.api_version = AP_RUNTIME_API_VERSION;
    assert(ap_runtime_get_critical_state(&runtime, &state) == AP_OK);
    teardown_snapshot_schedule(writer);
    assert(state.frame_sequence == ((UINT64_C(1) << 32u) | 222u));
    assert(state.kind == AP_EVENT_PIPELINE_ERROR);
    assert(state.severity == AP_EVENT_FATAL);
    assert(state.arg0 == 222 && state.arg1 == -333);
    assert(state.total_events == 2u);
}

static void test_metrics_counter_wrap_snapshot(void) {
    ap_runtime_metrics_t metrics = {0};
    pthread_t writer;
    memset(&runtime, 0, sizeof(runtime));
    init_runtime_atomics(&runtime);
    counter64_add(&runtime.processed_frames, (UINT64_C(17) << 32u) | UINT32_MAX);
    snapshot_counter = &runtime.processed_frames;
    snapshot_seq = &snapshot_counter->seq;
    snapshot_low = &snapshot_counter->lo;
    store_watch = &snapshot_counter->hi;
    writer = setup_snapshot_schedule();
    metrics.struct_size = sizeof(metrics);
    metrics.api_version = AP_RUNTIME_API_VERSION;
    assert(ap_runtime_read_metrics(&runtime, &metrics) == AP_OK);
    teardown_snapshot_schedule(writer);
    assert(metrics.processed_frames == (UINT64_C(18) << 32u));
}

int main(void) {
    test_output_status_ownership(AP_OK, AP_EINVAL);
    test_output_status_ownership(AP_EINVAL, AP_OK);
    test_command_boundary_budget(0u);
    test_command_boundary_budget(UINT_MAX - 1u);
    test_stop_keeps_worker_ownership_until_join();
    test_critical_snapshot(2u, 0u);
    test_critical_snapshot(2u, 1u);
    test_critical_snapshot(UINT_MAX - 1u, 0u);
    test_metrics_counter_wrap_snapshot();
    puts("audio-pipeline v2 runtime interleaving contracts: OK");
    return 0;
}
