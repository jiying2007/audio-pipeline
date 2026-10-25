#define _POSIX_C_SOURCE 200809L
/* Exactly seven registered native, zero-DSP fixtures; P02 is real exec ENOENT
 * and therefore has no fixture-image invocation. Shared protocol source is a
 * registered dependency, not another compilation unit or an external header.
 */
#define FE_F1_PROTOCOL_HELPERS_ONLY 1
#include "fe09_t3s3_f1_rss_observer.c"
#include <sys/types.h>
#include <sys/wait.h>

int main(int argc, char **argv) {
    const char *mode;
    int result = 0;
    if (argc != 3 || strcmp(argv[1], "--mode")) return 112;
    mode = argv[2];
    if (!strcmp(mode, "OVERSIZED_WIRE_BEFORE_ENTRY")) {
        char nonce[65], raw[257];
        int ordinal, control, ack;
        if (f1_environment(nonce, &ordinal, &control, &ack)) return 112;
        memset(raw, 'x', 256);
        raw[256] = '\n';
        if (f1_write_all(control, raw, sizeof(raw))) return 112;
        for (;;) pause();
    }
    if (!strcmp(mode, "EXEC_THEN_EOF_BEFORE_ENTRY")) {
        char nonce[65];
        int ordinal, control, ack;
        if (f1_environment(nonce, &ordinal, &control, &ack)) return 112;
        if (close(control) || close(ack)) return 112;
        return 0;
    }
    if (strcmp(mode, "COMPLETE") && strcmp(mode, "EXIT7") &&
        strcmp(mode, "STALL_AFTER_ENTRY") && strcmp(mode, "ONE_WAITED_DESCENDANT")) return 112;
    if (f1_checkpoint("ENTRY", 0)) return 111;
    if (!strcmp(mode, "STALL_AFTER_ENTRY")) for (;;) pause();
    if (!strcmp(mode, "ONE_WAITED_DESCENDANT")) {
        pid_t child, waited;
        int status;
        char line[256];
        int bytes;
        child = fork();
        if (child < 0) return 112;
        if (child == 0) _Exit(0);
        do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
        if (waited != child) return 112;
        bytes = snprintf(line, sizeof(line),
            "{\"kind\":\"F1_P07_CHILD_REPORTED_LINEAGE\",\"parent_pid\":%ld,"
            "\"fork_returned_pid\":%ld,\"wait_requested_pid\":%ld,\"wait_returned_pid\":%ld,"
            "\"raw_wait_status\":%d}\n", (long)getpid(), (long)child,
            (long)child, (long)waited, status);
        if (bytes <= 0 || (size_t)bytes >= sizeof(line) ||
            f1_write_all(STDOUT_FILENO, line, (size_t)bytes) ||
            !WIFEXITED(status) || WEXITSTATUS(status) != 0) return 112;
    }
    if (!strcmp(mode, "EXIT7")) result = 7;
    if (f1_checkpoint("RETURN", result)) return 111;
    return result;
}
