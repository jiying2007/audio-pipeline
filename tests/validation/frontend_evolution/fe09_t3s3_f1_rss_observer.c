#define _POSIX_C_SOURCE 200809L
/* Private F1 --wrap=main observer. It does not change the original main body.
 * Valid handshakes return the exact original main return value; RETURN precedes
 * runtime/atexit/sanitizer cleanup. No executable in this tranche has been run.
 */
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define F1_WIRE_CAP 256U

struct f1_field {
    char key[32];
    char text[72];
    int is_string;
    int64_t number;
};

static int f1_decimal(const char *text, int64_t *value) {
    char *end;
    long long parsed;
    const char *p = text;
    if (*p == '-') ++p;
    if (*p < '0' || *p > '9' || (*p == '0' && p[1] != '\0')) return -1;
    for (; *p; ++p) if (*p < '0' || *p > '9') return -1;
    errno = 0;
    parsed = strtoll(text, &end, 10);
    if (errno || *end || parsed < INT64_MIN || parsed > INT64_MAX) return -1;
    *value = (int64_t)parsed;
    return 0;
}

static int f1_string(const char **cursor, char *out, size_t cap) {
    const char *p = *cursor;
    size_t n = 0;
    if (*p++ != '"') return -1;
    while (*p && *p != '"') {
        unsigned char c = (unsigned char)*p++;
        /* Registered ASCII keys/values contain no escapes or control bytes. */
        if (c < 0x20 || c > 0x7e || c == '\\' || n + 1 >= cap) return -1;
        out[n++] = (char)c;
    }
    if (*p++ != '"') return -1;
    out[n] = '\0';
    *cursor = p;
    return 0;
}

static int f1_object(const char *raw, size_t bytes, struct f1_field *fields,
                     size_t cap, size_t *count) {
    const char *p = raw;
    size_t n = 0;
    if (!bytes || bytes > F1_WIRE_CAP || raw[bytes - 1] != '\n' ||
        raw[bytes] != '\0' || *p++ != '{') return -1;
    for (;;) {
        size_t i;
        if (n == cap || f1_string(&p, fields[n].key, sizeof(fields[n].key))) return -1;
        for (i = 0; i < n; ++i) if (!strcmp(fields[i].key, fields[n].key)) return -1;
        if (*p++ != ':') return -1;
        fields[n].is_string = (*p == '"');
        if (fields[n].is_string) {
            if (f1_string(&p, fields[n].text, sizeof(fields[n].text))) return -1;
        } else {
            char number[24];
            size_t used = 0;
            while (*p && *p != ',' && *p != '}') {
                if (used + 1 >= sizeof(number)) return -1;
                number[used++] = *p++;
            }
            number[used] = '\0';
            if (f1_decimal(number, &fields[n].number)) return -1;
        }
        ++n;
        if (*p == '}') {
            ++p;
            if (*p++ != '\n' || *p) return -1;
            *count = n;
            return 0;
        }
        if (*p++ != ',') return -1;
    }
}

static const struct f1_field *f1_lookup(const struct f1_field *fields, size_t n,
                                        const char *key) {
    size_t i;
    for (i = 0; i < n; ++i) if (!strcmp(fields[i].key, key)) return &fields[i];
    return NULL;
}

static int f1_is_text(const struct f1_field *fields, size_t n,
                       const char *key, const char *expected) {
    const struct f1_field *f = f1_lookup(fields, n, key);
    return f && f->is_string && !strcmp(f->text, expected);
}

static int f1_is_number(const struct f1_field *fields, size_t n,
                         const char *key, int64_t expected) {
    const struct f1_field *f = f1_lookup(fields, n, key);
    return f && !f->is_string && f->number == expected;
}

static int64_t f1_now(void) {
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value) || value.tv_sec < 0 ||
        value.tv_sec > INT64_MAX / 1000000000LL) return -1;
    return (int64_t)value.tv_sec * 1000000000LL + value.tv_nsec;
}

static int f1_write_all(int fd, const char *raw, size_t bytes) {
    while (bytes) {
        ssize_t used = write(fd, raw, bytes);
        if (used < 0 && errno == EINTR) continue;
        if (used <= 0) return -1;
        raw += used;
        bytes -= (size_t)used;
    }
    return 0;
}

static int f1_read_frame(int fd, char raw[F1_WIRE_CAP + 1], size_t *bytes) {
    size_t n = 0;
    for (;;) {
        char c;
        ssize_t used = read(fd, &c, 1);
        if (used < 0 && errno == EINTR) continue;
        if (used != 1 || n == F1_WIRE_CAP) return -1;
        raw[n++] = c;
        if (c == '\n') {
            raw[n] = '\0';
            *bytes = n;
            return 0;
        }
    }
}

#ifndef FE_F1_CORE_ONLY
static int f1_environment(char nonce[65], int *ordinal, int *control, int *ack) {
    const char *n = getenv("FE_F1_NONCE");
    const char *o = getenv("FE_F1_ORDINAL");
    const char *c = getenv("FE_F1_CONTROL_FD");
    const char *a = getenv("FE_F1_ACK_FD");
    int64_t oi, ci, ai;
    size_t i;
    if (!n || strlen(n) != 64 || !o || !c || !a ||
        f1_decimal(o, &oi) || f1_decimal(c, &ci) || f1_decimal(a, &ai) ||
        oi < 1 || oi > 36 || ci != 3 || ai != 4) return -1;
    for (i = 0; i < 64; ++i)
        if (!((n[i] >= '0' && n[i] <= '9') || (n[i] >= 'a' && n[i] <= 'f'))) return -1;
    memcpy(nonce, n, 65);
    *ordinal = (int)oi;
    *control = (int)ci;
    *ack = (int)ai;
    return 0;
}

static int f1_checkpoint(const char *phase, int return_code) {
    char nonce[65], wire[F1_WIRE_CAP + 1], response[F1_WIRE_CAP + 1];
    struct f1_field fields[8];
    int ordinal, control, ack, size;
    int64_t now;
    size_t bytes, count;
    const struct f1_field *ack_time;
    if (f1_environment(nonce, &ordinal, &control, &ack) || (now = f1_now()) < 0) return -1;
    if (!strcmp(phase, "ENTRY"))
        size = snprintf(wire, sizeof(wire),
            "{\"v\":1,\"phase\":\"ENTRY\",\"nonce\":\"%s\",\"ordinal\":%d,"
            "\"pid\":%ld,\"ppid\":%ld,\"monotonic_ns\":%" PRId64 "}\n",
            nonce, ordinal, (long)getpid(), (long)getppid(), now);
    else if (!strcmp(phase, "RETURN"))
        size = snprintf(wire, sizeof(wire),
            "{\"v\":1,\"phase\":\"RETURN\",\"nonce\":\"%s\",\"ordinal\":%d,"
            "\"pid\":%ld,\"ppid\":%ld,\"monotonic_ns\":%" PRId64 ",\"return_code\":%d}\n",
            nonce, ordinal, (long)getpid(), (long)getppid(), now, return_code);
    else return -1;
    if (size <= 0 || (size_t)size > F1_WIRE_CAP ||
        f1_write_all(control, wire, (size_t)size) ||
        f1_read_frame(ack, response, &bytes) ||
        f1_object(response, bytes, fields, 8, &count) || count != 8) return -1;
    ack_time = f1_lookup(fields, count, "monotonic_ns");
    return !(f1_is_number(fields, count, "v", 1) &&
             f1_is_text(fields, count, "phase", "ACK") &&
             f1_is_text(fields, count, "for_phase", phase) &&
             f1_is_text(fields, count, "nonce", nonce) &&
             f1_is_number(fields, count, "ordinal", ordinal) &&
             f1_is_number(fields, count, "child_pid", getpid()) &&
             f1_is_number(fields, count, "launcher_pid", getppid()) &&
             ack_time && !ack_time->is_string && ack_time->number >= now &&
             ack_time->number <= f1_now());
}

#ifndef FE_F1_PROTOCOL_HELPERS_ONLY
int __real_main(int argc, char **argv);

int __wrap_main(int argc, char **argv) {
    int result;
    if (f1_checkpoint("ENTRY", 0)) _Exit(111);
    result = __real_main(argc, argv);
    if (f1_checkpoint("RETURN", result)) _Exit(111);
    return result;
}
#endif
#endif
