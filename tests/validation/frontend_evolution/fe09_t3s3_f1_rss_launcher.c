#define _GNU_SOURCE
/* F1 native launcher: ordinary fork, exact execve, bounded checkpoints and
 * exact-child wait4. No Python, shell, PATH lookup, RSS subtraction or retry.
 * Bootstrap permits compilation only; this image has not been executed.
 */
#define FE_F1_CORE_ONLY 1
#define FE_F1_PROTOCOL_HELPERS_ONLY 1
#include "fe09_t3s3_f1_rss_observer.c"
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>

#define F1_STATUS_CAP 8192U
#define F1_STAT_CAP 1536U
#define F1_IDENTITY_CAP 4096U
#define F1_TRANSCRIPT_CAP 1024U
#define F1_TARGET_LOG_CAP 1048576U
#define F1_EXE_CAP 33554432U
#define F1_CHECKPOINT_NS INT64_C(2000000000)

struct f1_sha256 {
    uint32_t h[8];
    uint64_t bytes;
    unsigned char block[64];
    size_t used;
};

static uint32_t f1_rotr(uint32_t x, unsigned n) { return (x >> n) | (x << (32U - n)); }

static void f1_sha_block(struct f1_sha256 *s, const unsigned char *p) {
    static const uint32_t k[64] = {
        0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
        0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
        0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
        0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
        0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
        0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
        0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
        0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U
    };
    uint32_t w[64], a,b,c,d,e,f,g,h;
    size_t i;
    for (i = 0; i < 16; ++i)
        w[i] = ((uint32_t)p[i*4] << 24) | ((uint32_t)p[i*4+1] << 16) |
               ((uint32_t)p[i*4+2] << 8) | (uint32_t)p[i*4+3];
    for (i = 16; i < 64; ++i) {
        uint32_t x = w[i-15], y = w[i-2];
        w[i] = w[i-16] + (f1_rotr(x,7)^f1_rotr(x,18)^(x>>3)) + w[i-7] +
               (f1_rotr(y,17)^f1_rotr(y,19)^(y>>10));
    }
    a=s->h[0]; b=s->h[1]; c=s->h[2]; d=s->h[3];
    e=s->h[4]; f=s->h[5]; g=s->h[6]; h=s->h[7];
    for (i = 0; i < 64; ++i) {
        uint32_t t1 = h + (f1_rotr(e,6)^f1_rotr(e,11)^f1_rotr(e,25)) +
                      ((e&f)^((~e)&g)) + k[i] + w[i];
        uint32_t t2 = (f1_rotr(a,2)^f1_rotr(a,13)^f1_rotr(a,22)) + ((a&b)^(a&c)^(b&c));
        h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    s->h[0]+=a; s->h[1]+=b; s->h[2]+=c; s->h[3]+=d;
    s->h[4]+=e; s->h[5]+=f; s->h[6]+=g; s->h[7]+=h;
}

static void f1_sha_init(struct f1_sha256 *s) {
    static const uint32_t initial[8] = {0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,
        0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U};
    memcpy(s->h, initial, sizeof(initial)); s->bytes=0; s->used=0;
}

static void f1_sha_update(struct f1_sha256 *s, const void *raw, size_t bytes) {
    const unsigned char *p = raw;
    s->bytes += bytes;
    while (bytes) {
        size_t take = 64 - s->used;
        if (take > bytes) take = bytes;
        memcpy(s->block + s->used, p, take);
        s->used += take; p += take; bytes -= take;
        if (s->used == 64) { f1_sha_block(s, s->block); s->used=0; }
    }
}

static void f1_sha_finish(struct f1_sha256 *s, char hex[65]) {
    static const char digits[] = "0123456789abcdef";
    uint64_t bits = s->bytes * 8U;
    unsigned char end[128] = {0x80};
    size_t pad = s->used < 56 ? 56 - s->used : 120 - s->used, i;
    for (i=0; i<8; ++i) end[pad+i]=(unsigned char)(bits >> (56-8*i));
    f1_sha_update(s, end, pad+8);
    for (i=0; i<32; ++i) {
        unsigned char byte=(unsigned char)(s->h[i/4] >> (24-8*(i%4)));
        hex[2*i]=digits[byte>>4]; hex[2*i+1]=digits[byte&15];
    }
    hex[64]='\0';
}

static void f1_hash(const void *raw, size_t bytes, char hex[65]) {
    struct f1_sha256 s; f1_sha_init(&s); f1_sha_update(&s,raw,bytes); f1_sha_finish(&s,hex);
}

struct f1_buffer { char *raw; size_t cap, used; int bad; };

static void f1_append(struct f1_buffer *b, const char *format, ...) {
    int n;
    va_list args;
    if (b->bad) return;
    va_start(args,format);
    n=vsnprintf(b->raw+b->used,b->cap-b->used,format,args);
    va_end(args);
    if (n<0 || (size_t)n>=b->cap-b->used) { b->bad=1; return; }
    b->used+=(size_t)n;
}

static int f1_utf8(const unsigned char *raw, size_t bytes) {
    size_t i=0;
    while(i<bytes) {
        uint32_t value;unsigned rest;unsigned char first=raw[i++];
        if(first<0x80)continue;
        if(first>=0xc2 && first<=0xdf){value=first&31U;rest=1;}
        else if(first>=0xe0 && first<=0xef){value=first&15U;rest=2;}
        else if(first>=0xf0 && first<=0xf4){value=first&7U;rest=3;}
        else return -1;
        if(bytes-i<rest)return -1;
        {
            unsigned n;
            for(n=0;n<rest;++n){unsigned char c=raw[i++];if((c&0xc0U)!=0x80U)return -1;value=(value<<6)|(c&63U);}
        }
        if((rest==2 && value<0x800) || (rest==3 && value<0x10000) ||
           value>0x10ffff || (value>=0xd800 && value<=0xdfff))return -1;
    }
    return 0;
}

static void f1_quoted(struct f1_buffer *b, const char *raw, size_t bytes) {
    size_t i;
    if(f1_utf8((const unsigned char *)raw,bytes)){b->bad=1;return;}
    f1_append(b,"\"");
    for (i=0; i<bytes; ++i) {
        unsigned char c=(unsigned char)raw[i];
        if (c=='"' || c=='\\') f1_append(b,"\\%c",c);
        else if (c=='\n') f1_append(b,"\\n");
        else if (c=='\r') f1_append(b,"\\r");
        else if (c=='\t') f1_append(b,"\\t");
        else if (c<0x20) f1_append(b,"\\u%04x",(unsigned)c);
        else f1_append(b,"%c",c);
    }
    f1_append(b,"\"");
}

struct f1_options {
    const char *directory, *nonce, *binding, *host_hash;
    char **target;
    int ordinal, engineering;
    int64_t origin, work_deadline, final_deadline;
};

struct f1_state {
    struct f1_options option;
    int directory, diagnostic, target_log, control, ack, error_pipe, output_pipe;
    int error_eof, output_eof, reaped, wait_status, exec_errno, exec_stage;
    unsigned char exec_raw[8];
    size_t exec_bytes, target_log_bytes, target_log_observed;
    unsigned diagnostic_lines;
    pid_t child, waited;
    struct rusage usage;
    int64_t fork_before, fork_after, wait_before, wait_after;
    int64_t start_ticks, snapshot_before, snapshot_after, last_child_time, last_ack_time;
    char namespace_hash[65], self_hash[65];
    dev_t entry_device;
    ino_t entry_inode;
    char entry_exe_path[513];
    int entry_image_observed;
    const char *reason, *phase, *overflow_member;
    size_t observed_bytes, retained_bytes;
    int returned_code, completed_phases;
};

static int f1_hex(const char *raw) {
    size_t i;
    if (!raw || strlen(raw)!=64) return 0;
    for (i=0;i<64;++i) if (!((raw[i]>='0'&&raw[i]<='9')||(raw[i]>='a'&&raw[i]<='f'))) return 0;
    return 1;
}

static int f1_options(int argc, char **argv, struct f1_options *o) {
    unsigned seen=0;
    int i;
    int64_t ordinal=0;
    memset(o,0,sizeof(*o));
    for (i=1;i<argc;++i) {
        unsigned bit=0;
        const char *key=argv[i], *value;
        if (!strcmp(key,"--")) { ++i; break; }
        if (++i==argc) return -1;
        value=argv[i];
        if (!strcmp(key,"--kind")) {
            bit=1U; if (!strcmp(value,"engineering")) o->engineering=1;
            else if (strcmp(value,"science")) return -1;
        } else if (!strcmp(key,"--output")) { bit=2U; o->directory=value; }
        else if (!strcmp(key,"--nonce")) { bit=4U; o->nonce=value; }
        else if (!strcmp(key,"--ordinal")) { bit=8U; if(f1_decimal(value,&ordinal))return -1; }
        else if (!strcmp(key,"--case-binding-sha256")) { bit=16U; o->binding=value; }
        else if (!strcmp(key,"--invocation-started-monotonic-ns")) { bit=32U; if(f1_decimal(value,&o->origin))return -1; }
        else if (!strcmp(key,"--work-deadline-monotonic-ns")) { bit=64U; if(f1_decimal(value,&o->work_deadline))return -1; }
        else if (!strcmp(key,"--final-deadline-monotonic-ns")) { bit=128U; if(f1_decimal(value,&o->final_deadline))return -1; }
        else if (!strcmp(key,"--host-executable-sha256")) { bit=256U; o->host_hash=value; }
        else return -1;
        if (seen&bit) return -1;
        seen|=bit;
    }
    if (seen!=511U || i>=argc || argv[i][0]!='/' || argc-i>32 ||
        ordinal<1 || ordinal>(o->engineering?7:36) ||
        !o->directory || o->directory[0]!='/' || strlen(o->directory)>512 ||
        strstr(o->directory,"/../") || strstr(o->directory,"/./") ||
        !f1_hex(o->nonce) || !f1_hex(o->binding) || !f1_hex(o->host_hash) ||
        o->origin<0 || o->work_deadline<=o->origin ||
        o->final_deadline<o->work_deadline || f1_now()<o->origin ||
        f1_now()>=o->work_deadline) return -1;
    if (o->engineering) {
        if (o->work_deadline-o->origin!=INT64_C(800000000) ||
            o->final_deadline-o->origin!=INT64_C(1000000000)) return -1;
    } else if (o->final_deadline-o->origin>INT64_C(29500000000) ||
               o->final_deadline-o->work_deadline!=INT64_C(500000000)) return -1;
    /* Science keeps 500ms inside this native deadline for direct-child reap.
     * The owning Python collector retains a further 500ms inside the original
     * <=30s invocation for launcher wait4, owned-group cleanup and encoding.
     * The engineering 800ms/1s contract above is unchanged. */
    o->ordinal=(int)ordinal; o->target=&argv[i];
    if(o->engineering) {
        static const char *modes[7]={"COMPLETE",NULL,"EXIT7","STALL_AFTER_ENTRY",
            "OVERSIZED_WIRE_BEFORE_ENTRY","EXEC_THEN_EOF_BEFORE_ENTRY","ONE_WAITED_DESCENDANT"};
        if(o->ordinal==2) {
            struct stat absent;
            size_t path_bytes=strlen(o->directory);
            char expected[529];
            if(argc-i!=1 || path_bytes<4 || strcmp(o->directory+path_bytes-4,"/rss"))return -1;
            if(snprintf(expected,sizeof(expected),"%.*s/absent-target",(int)(path_bytes-4),o->directory)<0 ||
               strcmp(expected,o->target[0]))return -1;
            if(lstat(o->target[0],&absent)==0 || errno!=ENOENT)return -1;
        } else if(argc-i!=3 || strcmp(o->target[1],"--mode") ||
                  strcmp(o->target[2],modes[o->ordinal-1]))return -1;
    }
    {
        char raw[2049]; struct f1_buffer b={raw,sizeof(raw),0,0};
        f1_append(&b,"[");
        for (;i<argc;++i) { if (i!=(int)(o->target-argv))f1_append(&b,","); f1_quoted(&b,argv[i],strlen(argv[i])); }
        f1_append(&b,"]"); if(b.bad || b.used>2048)return -1;
    }
    return 0;
}

static int f1_member(struct f1_state *s, const char *name, const char *raw, size_t bytes, size_t cap) {
    int fd, result;
    if (bytes>cap) return -1;
    fd=openat(s->directory,name,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if (fd<0) return -1;
    result=f1_write_all(fd,raw,bytes);
    if (close(fd)) result=-1;
    return result;
}

static void f1_log(struct f1_state *s, const char *reason, const char *phase) {
    char raw[256];
    int bytes;
    if (s->diagnostic<0 || s->diagnostic_lines>=24) return;
    bytes=snprintf(raw,sizeof(raw),
        "reason=%s phase=%s pid=%ld time_ns=%" PRId64 " observed=%zu retained=%zu\n",
        reason,phase?phase:"NONE",(long)s->child,f1_now(),s->observed_bytes,s->retained_bytes);
    if (bytes>0 && (size_t)bytes<sizeof(raw)) {
        if (!f1_write_all(s->diagnostic,raw,(size_t)bytes)) ++s->diagnostic_lines;
    }
}

static void f1_fail(struct f1_state *s, const char *reason) {
    if (!s->reason) { s->reason=reason; f1_log(s,reason,s->phase); }
}

static int f1_nonblocking(int fd) {
    int value=fcntl(fd,F_GETFL);
    return value<0 ? -1 : fcntl(fd,F_SETFL,value|O_NONBLOCK);
}

static void f1_wait_once(struct f1_state *s) {
    pid_t result;
    if (s->reaped || s->child<=0) return;
    if (!s->wait_before) s->wait_before=f1_now();
    result=wait4(s->child,&s->wait_status,WNOHANG,&s->usage);
    if (result==s->child) {
        s->waited=result; s->reaped=1; s->wait_after=f1_now();
    } else if (result<0 && errno!=EINTR) f1_fail(s,"F1R1_OWNED_WAIT4_FAILED");
}

static void f1_drain(struct f1_state *s) {
    char raw[4096];
    ssize_t used;
    if (!s->output_eof && s->output_pipe>=0) {
        for (;;) {
            used=read(s->output_pipe,raw,sizeof(raw));
            if (used<0 && errno==EINTR) continue;
            if (used<0 && (errno==EAGAIN || errno==EWOULDBLOCK)) break;
            if (used<=0) { s->output_eof=1; if(used<0)f1_fail(s,"F1R1_TARGET_LOG_READ_FAILED"); break; }
            {
                size_t available=F1_TARGET_LOG_CAP-s->target_log_bytes;
                size_t retained=(size_t)used<available?(size_t)used:available;
                s->target_log_observed+=(size_t)used;
                if (retained && f1_write_all(s->target_log,raw,retained)) f1_fail(s,"F1R1_TARGET_LOG_WRITE_FAILED");
                s->target_log_bytes+=retained;
                if (retained!=(size_t)used) {
                    s->overflow_member="target.log";s->observed_bytes=s->target_log_observed;
                    s->retained_bytes=s->target_log_bytes;
                    f1_fail(s,"F1R1_TARGET_LOG_BYTES_LIMIT"); break;
                }
            }
            if (f1_now()>=s->option.work_deadline) break;
        }
    }
    if (!s->error_eof && s->error_pipe>=0) {
        for (;;) {
            unsigned char extra;
            void *place=s->exec_bytes<sizeof(s->exec_raw)?(void *)(s->exec_raw+s->exec_bytes):(void *)&extra;
            size_t available=s->exec_bytes<sizeof(s->exec_raw)?sizeof(s->exec_raw)-s->exec_bytes:1;
            used=read(s->error_pipe,place,available);
            if (used<0 && errno==EINTR) continue;
            if (used<0 && (errno==EAGAIN || errno==EWOULDBLOCK)) break;
            if (used<=0) {
                s->error_eof=1;
                if(used<0)f1_fail(s,"F1R1_EXEC_ERROR_PIPE_READ_FAILED");
                else f1_log(s,s->exec_bytes?"EXEC_ERROR_PIPE_EOF_WITH_BYTES":"EXEC_ERROR_PIPE_EOF_EMPTY",s->phase);
                break;
            }
            if (s->exec_bytes+(size_t)used>sizeof(s->exec_raw)) { f1_fail(s,"F1R1_EXEC_ERROR_PIPE_FORMAT");break; }
            s->exec_bytes+=(size_t)used;
            if (s->exec_bytes==sizeof(s->exec_raw)) {
                int32_t words[2]; memcpy(words,s->exec_raw,sizeof(words));
                s->exec_stage=words[0];s->exec_errno=words[1];
                if ((s->exec_stage!=1 && s->exec_stage!=2) || s->exec_errno<=0)
                    f1_fail(s,"F1R1_EXEC_ERROR_PIPE_FORMAT");
            }
        }
    }
    f1_wait_once(s);
}

static int f1_poll(struct f1_state *s, int64_t deadline) {
    struct pollfd fds[3];
    int64_t now=f1_now(), remaining;
    int millis, result;
    if (now<0 || now>=deadline) return 0;
    remaining=deadline-now;
    millis=(int)((remaining+999999)/1000000);
    if (millis>10) millis=10;
    fds[0].fd=s->control; fds[0].events=POLLIN|POLLHUP; fds[0].revents=0;
    fds[1].fd=s->output_eof?-1:s->output_pipe; fds[1].events=POLLIN|POLLHUP; fds[1].revents=0;
    fds[2].fd=s->error_eof?-1:s->error_pipe; fds[2].events=POLLIN|POLLHUP; fds[2].revents=0;
    do { result=poll(fds,3,millis); } while(result<0 && errno==EINTR && f1_now()<deadline);
    if (result<0) { f1_fail(s,"F1R1_POLL_FAILED");return -1; }
    f1_drain(s);
    return 1;
}

static int f1_frame(struct f1_state *s, char raw[257], size_t *bytes, int phase_index) {
    size_t n=0;
    int64_t deadline=s->option.work_deadline, start=f1_now();
    if (phase_index<2 && deadline-start>F1_CHECKPOINT_NS) deadline=start+F1_CHECKPOINT_NS;
    for (;;) {
        char c;
        ssize_t used;
        f1_drain(s);
        if (s->reason) return -1;
        used=read(s->control,&c,1);
        if (used<0 && errno==EINTR) continue;
        if (used==1) {
            if (n==256) {
                raw[256]='\0';*bytes=256;
                s->overflow_member="control";s->observed_bytes=257;s->retained_bytes=256;
                f1_fail(s,"F1R1_WIRE_BYTES_LIMIT");return -1;
            }
            raw[n++]=c;
            if(n==1 && deadline-f1_now()>F1_CHECKPOINT_NS) deadline=f1_now()+F1_CHECKPOINT_NS;
            if(c=='\n') { raw[n]='\0';*bytes=n;return 0; }
        } else if (used==0) {
            /* EOF must still bind the real exec error and final owned wait. */
            f1_drain(s);
            if (s->exec_bytes && s->exec_bytes!=8) f1_fail(s,"F1R1_EXEC_ERROR_PIPE_FORMAT");
            else if(s->exec_errno) f1_fail(s,s->exec_stage==2?"F1R1_EXECVE_FAILED":"F1R1_CHILD_SETUP_FAILED");
            else f1_fail(s,phase_index==1?"F1R1_ENTRY_REQUIRED_AFTER_EXEC":"F1R1_CHECKPOINT_REQUIRED");
            raw[n]='\0';*bytes=n;return -1;
        } else if(errno!=EAGAIN && errno!=EWOULDBLOCK) {
            f1_fail(s,"F1R1_CONTROL_READ_FAILED");return -1;
        }
        if (f1_now()>=deadline) {
            f1_fail(s,deadline==s->option.work_deadline?
                (s->option.engineering?"F1R1_ENGINEERING_INVOCATION_TIMEOUT":"F1R1_SCIENCE_INVOCATION_TIMEOUT"):
                "F1R1_CHECKPOINT_TIMEOUT");
            raw[n]='\0';*bytes=n;return -1;
        }
        if (used<0 && f1_poll(s,deadline)<0) return -1;
    }
}

static int f1_file_prefix(const char *path, char *raw, size_t cap, size_t *bytes, int *overflow) {
    int fd=open(path,O_RDONLY|O_CLOEXEC);
    size_t n=0;
    if(fd<0)return -1;
    *overflow=0;
    while(n<=cap) {
        ssize_t used=read(fd,raw+n,cap+1-n);
        if(used<0 && errno==EINTR)continue;
        if(used<0){close(fd);return -1;}
        if(used==0)break;
        n+=(size_t)used;
        if(n>cap){*overflow=1;break;}
    }
    if(close(fd))return -1;
    *bytes=n>cap?cap:n;raw[*bytes]='\0';return 0;
}

static int f1_executable_hash(const char *path, char hash[65], struct stat *identity,
                               int64_t deadline) {
    struct f1_sha256 s;
    struct stat after;
    unsigned char raw[16384];
    size_t total=0;
    int fd=open(path,O_RDONLY|O_CLOEXEC), result=-1;
    if(fd<0)return -1;
    if(fstat(fd,identity) || !S_ISREG(identity->st_mode) || identity->st_size<0 ||
       identity->st_size>(off_t)F1_EXE_CAP)goto finish;
    f1_sha_init(&s);
    for(;;) {
        ssize_t used;
        if(f1_now()>=deadline)goto finish;
        used=read(fd,raw,sizeof(raw));
        if(used<0 && errno==EINTR)continue;
        if(used<0)goto finish;
        if(used==0)break;
        total+=(size_t)used;if(total>F1_EXE_CAP)goto finish;
        f1_sha_update(&s,raw,(size_t)used);
    }
    if(fstat(fd,&after) || after.st_dev!=identity->st_dev || after.st_ino!=identity->st_ino ||
       after.st_size!=identity->st_size || total!=(size_t)identity->st_size)goto finish;
    f1_sha_finish(&s,hash);result=0;
finish:
    if(close(fd))result=-1;
    return result;
}

static int f1_stat_identity(const char *raw, pid_t pid, pid_t ppid, int64_t *ticks) {
    char copy[F1_STAT_CAP+1], *open, *close, *cursor, *save;
    int field;
    int64_t actual;
    memcpy(copy,raw,strlen(raw)+1);
    open=strchr(copy,'(');close=strrchr(copy,')');
    if(!open || !close || open<=copy || close<=open || open[-1]!=' ')return -1;
    open[-1]='\0';if(f1_decimal(copy,&actual)||actual!=pid)return -1;
    cursor=close+1;if(*cursor++!=' ' || !*cursor || cursor[1]!=' ')return -1;
    cursor+=2;
    for(field=4;field<=22;++field) {
        char *token=strtok_r(field==4?cursor:NULL," \n",&save);
        if(!token || f1_decimal(token,&actual))return -1;
        if(field==4 && actual!=ppid)return -1;
        if(field==22){if(actual<0)return -1;*ticks=actual;}
    }
    return 0;
}

static int f1_status_identity(const char *raw, pid_t pid, pid_t ppid,
                               char namespace_hash[65], int postexec) {
    char copy[F1_STATUS_CAP+1], namespace_json[F1_STATUS_CAP+1], *save, *line;
    struct f1_buffer b={namespace_json,sizeof(namespace_json),0,0};
    unsigned seen=0;
    memcpy(copy,raw,strlen(raw)+1);
    for(line=strtok_r(copy,"\n",&save);line;line=strtok_r(NULL,"\n",&save)) {
        char *colon=strchr(line,':'), *p, *end;
        unsigned bit=0;
        int64_t value;
        if(!colon)continue;
        *colon='\0';p=colon+1;while(*p==' '||*p=='\t')++p;
        if(!strcmp(line,"Pid"))bit=1;
        else if(!strcmp(line,"PPid"))bit=2;
        else if(!strcmp(line,"NSpid"))bit=4;
        else if(!strcmp(line,"VmHWM"))bit=8;
        else if(!strcmp(line,"VmRSS"))bit=16;
        else if(!strcmp(line,"Threads"))bit=32;
        else continue;
        if(seen&bit)return -1;
        seen|=bit;
        if(bit==4) {
            unsigned count=0;
            f1_append(&b,"[");
            while(*p) {
                char number[24];size_t n=0;
                while(*p==' '||*p=='\t')++p;
                if(!*p)break;
                while(*p && *p!=' '&&*p!='\t'){if(n+1>=sizeof(number))return -1;number[n++]=*p++;}
                number[n]='\0';if(f1_decimal(number,&value)||value<=0||value>INT_MAX)return -1;
                if(count==0 && value!=pid)return -1;
                if(count++)f1_append(&b,",");
                f1_append(&b,"%" PRId64,value);
            }
            f1_append(&b,"]");if(!count||b.bad)return -1;
            f1_hash(b.raw,b.used,namespace_hash);
            continue;
        }
        end=p;while(*end && *end!=' '&&*end!='\t')++end;
        if(*end){*end++='\0';while(*end==' '||*end=='\t')++end;}
        if(f1_decimal(p,&value)||value<0)return -1;
        if(bit==1 && value!=pid)return -1;
        if(bit==2 && value!=ppid)return -1;
        if(bit==32 && value<=0)return -1;
        if((bit==8||bit==16) && (strcmp(end,"kB") || (postexec && value<=0)))return -1;
        if((bit==1||bit==2||bit==32) && *end)return -1;
    }
    return seen==63?0:-1;
}

static int f1_transcript(struct f1_state *s, int sequence, const char *direction,
                          const char *phase, const char *wire, size_t bytes,
                          int64_t at, int observation) {
    char raw[F1_TRANSCRIPT_CAP+1], name[32], hash[65];
    struct f1_buffer b={raw,sizeof(raw),0,0};
    f1_hash(wire,bytes,hash);
    f1_append(&b,"{\"schema_version\":1,\"sequence\":%d,\"direction\":\"%s\","
              "\"phase\":\"%s\",\"wire_bytes\":",sequence,direction,phase);
    f1_quoted(&b,wire,bytes);
    f1_append(&b,",\"wire_sha256\":\"%s\",\"wire_byte_count\":%zu,"
              "\"channel_owner_pid\":%ld,\"peer_pid\":%ld,"
              "\"received_or_sent_monotonic_ns\":%" PRId64 ","
              "\"observation_started_monotonic_ns\":",hash,bytes,(long)getpid(),(long)s->child,at);
    if(observation)f1_append(&b,"%" PRId64,s->snapshot_before);else f1_append(&b,"null");
    f1_append(&b,",\"observation_finished_monotonic_ns\":");
    if(observation)f1_append(&b,"%" PRId64,s->snapshot_after);else f1_append(&b,"null");
    f1_append(&b,"}\n");
    snprintf(name,sizeof(name),"control-%d.json",sequence);
    return b.bad?-1:f1_member(s,name,b.raw,b.used,F1_TRANSCRIPT_CAP);
}

static int f1_snapshot(struct f1_state *s, const char *phase, int64_t deadline) {
    char path[80], status[F1_STATUS_CAP+2], stat_raw[F1_STAT_CAP+2], exe[514];
    char status_hash[65], stat_hash[65], exe_hash[65], namespace_hash[65], name[64];
    char raw[F1_IDENTITY_CAP+1];
    struct f1_buffer b={raw,sizeof(raw),0,0};
    struct stat identity;
    size_t status_bytes=0, stat_bytes=0;
    int status_overflow=0, stat_overflow=0, ok=1;
    int64_t ticks=-1;
    ssize_t exe_bytes;
    s->snapshot_before=f1_now();
    snprintf(path,sizeof(path),"/proc/%ld/status",(long)s->child);
    if(f1_file_prefix(path,status,F1_STATUS_CAP,&status_bytes,&status_overflow))return -1;
    snprintf(name,sizeof(name),"%s.status",phase);
    if(f1_member(s,name,status,status_bytes,F1_STATUS_CAP))return -1;
    f1_hash(status,status_bytes,status_hash);
    if(status_overflow){s->overflow_member="proc_status";s->observed_bytes=8193;s->retained_bytes=8192;f1_fail(s,"F1R1_PROC_STATUS_BYTES_LIMIT");ok=0;}
    snprintf(path,sizeof(path),"/proc/%ld/stat",(long)s->child);
    if(f1_file_prefix(path,stat_raw,F1_STAT_CAP,&stat_bytes,&stat_overflow))return -1;
    f1_hash(stat_raw,stat_bytes,stat_hash);
    if(stat_overflow){s->overflow_member="proc_stat";s->observed_bytes=1537;s->retained_bytes=1536;f1_fail(s,"F1R1_PROC_STAT_BYTES_LIMIT");ok=0;}
    memset(namespace_hash,0,sizeof(namespace_hash));
    if(!status_overflow && f1_status_identity(status,s->child,getpid(),namespace_hash,strcmp(phase,"PREEXEC")!=0))ok=0;
    if(!stat_overflow && f1_stat_identity(stat_raw,s->child,getpid(),&ticks))ok=0;
    if(s->start_ticks>=0 && ticks!=s->start_ticks)ok=0;
    if(s->namespace_hash[0] && strcmp(namespace_hash,s->namespace_hash))ok=0;
    snprintf(path,sizeof(path),"/proc/%ld/exe",(long)s->child);
    exe_bytes=readlink(path,exe,513);
    if(exe_bytes<0)return -1;
    if(exe_bytes>512){exe_bytes=512;s->overflow_member="exe_path";s->observed_bytes=513;s->retained_bytes=512;f1_fail(s,"F1R1_EXE_PATH_BYTES_LIMIT");ok=0;}
    exe[exe_bytes]='\0';
    memset(&identity,0,sizeof(identity));memset(exe_hash,0,sizeof(exe_hash));
    if(f1_executable_hash(path,exe_hash,&identity,deadline))ok=0;
    if(strcmp(exe_hash,!strcmp(phase,"PREEXEC")?s->self_hash:s->option.host_hash))ok=0;
    if(!strcmp(phase,"RETURN") && (!s->entry_image_observed || identity.st_dev!=s->entry_device ||
        identity.st_ino!=s->entry_inode || strcmp(exe,s->entry_exe_path)))ok=0;
    s->snapshot_after=f1_now();if(s->snapshot_after>deadline)ok=0;
    f1_append(&b,"{\"schema_version\":1,\"phase\":\"%s\",\"nonce\":\"%s\",\"ordinal\":%d,"
              "\"case_binding_sha256\":\"%s\",\"pid\":%ld,\"ppid\":%ld,\"start_ticks\":",
              phase,s->option.nonce,s->option.ordinal,s->option.binding,(long)s->child,(long)getpid());
    if(ticks>=0)f1_append(&b,"%" PRId64,ticks);else f1_append(&b,"null");
    f1_append(&b,",\"namespace_mapping_sha256\":");
    if(namespace_hash[0])f1_quoted(&b,namespace_hash,64);else f1_append(&b,"null");
    f1_append(&b,",\"status_sha256\":\"%s\",\"stat_raw\":",status_hash);f1_quoted(&b,stat_raw,stat_bytes);
    f1_append(&b,",\"stat_sha256\":\"%s\",\"exe_path\":",stat_hash);f1_quoted(&b,exe,(size_t)exe_bytes);
    f1_append(&b,",\"exe_sha256\":");if(exe_hash[0])f1_quoted(&b,exe_hash,64);else f1_append(&b,"null");
    f1_append(&b,",\"exe_device\":%ju,\"exe_inode\":%ju,"
              "\"observation_started_monotonic_ns\":%" PRId64 ","
              "\"observation_finished_monotonic_ns\":%" PRId64 ","
              "\"complete_original\":%s,\"overflow\":%s}\n",
              (uintmax_t)identity.st_dev,(uintmax_t)identity.st_ino,s->snapshot_before,s->snapshot_after,
              ok?"true":"false",s->overflow_member?"true":"false");
    snprintf(name,sizeof(name),"%s.identity.json",phase);
    if(b.bad || f1_member(s,name,b.raw,b.used,F1_IDENTITY_CAP)) { f1_fail(s,"F1R1_IDENTITY_BYTES_OR_WRITE_LIMIT");return -1; }
    if(!ok){f1_fail(s,"F1R1_RAW_PROC_OR_IMAGE_IDENTITY");return -1;}
    if(s->start_ticks<0){s->start_ticks=ticks;memcpy(s->namespace_hash,namespace_hash,65);}
    if(!strcmp(phase,"ENTRY")) {
        s->entry_device=identity.st_dev;s->entry_inode=identity.st_ino;
        memcpy(s->entry_exe_path,exe,(size_t)exe_bytes+1);s->entry_image_observed=1;
    }
    return 0;
}

static int f1_validate_message(struct f1_state *s, const char *raw, size_t bytes,
                                const char *phase, int64_t received) {
    struct f1_field fields[8];size_t count;
    const struct f1_field *stamp, *special;
    if(f1_object(raw,bytes,fields,8,&count) || count!=(strcmp(phase,"ENTRY")?8U:7U) ||
       !f1_is_number(fields,count,"v",1) || !f1_is_text(fields,count,"phase",phase) ||
       !f1_is_text(fields,count,"nonce",s->option.nonce) ||
       !f1_is_number(fields,count,"ordinal",s->option.ordinal) ||
       !f1_is_number(fields,count,"pid",s->child) || !f1_is_number(fields,count,"ppid",getpid()))return -1;
    stamp=f1_lookup(fields,count,"monotonic_ns");
    if(!stamp || stamp->is_string || stamp->number<s->fork_before ||
       stamp->number<s->last_child_time || stamp->number<s->last_ack_time || stamp->number>received)return -1;
    s->last_child_time=stamp->number;
    if(!strcmp(phase,"PREEXEC")) {
        special=f1_lookup(fields,count,"rss_kib");if(!special||special->is_string||special->number<0)return -1;
    } else if(!strcmp(phase,"RETURN")) {
        special=f1_lookup(fields,count,"return_code");
        if(!special||special->is_string||special->number<INT32_MIN||special->number>INT32_MAX)return -1;
        s->returned_code=(int)special->number;
    }
    return 0;
}

static void f1_child_error(int stage, int error) {
    int32_t words[2];words[0]=(int32_t)stage;words[1]=(int32_t)error;
    (void)f1_write_all(5,(const char *)words,sizeof(words));
    _Exit(stage==2?127:126);
}

static void f1_child(const struct f1_options *o, int control, int ack, int error,
                       int output, int input) {
    char wire[257], reply[257], nonce_env[80], ordinal_env[40];
    char *environment[9];
    struct rusage usage;
    struct f1_field fields[8];
    const struct f1_field *ack_time;
    int bytes;
    int64_t stamp;
    size_t n,count;
    if(dup2(error,5)<0)_Exit(126);
    if(fcntl(5,F_SETFD,FD_CLOEXEC)<0 || dup2(control,3)<0 || dup2(ack,4)<0 ||
       dup2(output,STDOUT_FILENO)<0 || dup2(output,STDERR_FILENO)<0 || dup2(input,STDIN_FILENO)<0 ||
       fcntl(3,F_SETFD,0)<0 || fcntl(4,F_SETFD,0)<0)f1_child_error(1,errno);
#ifdef SYS_close_range
    if(syscall(SYS_close_range,6U,~0U,0U)<0)f1_child_error(1,errno);
#else
    f1_child_error(1,ENOSYS);
#endif
    if(getrusage(RUSAGE_SELF,&usage)<0 || (stamp=f1_now())<0)f1_child_error(1,errno?errno:EIO);
    bytes=snprintf(wire,sizeof(wire),
        "{\"v\":1,\"phase\":\"PREEXEC\",\"nonce\":\"%s\",\"ordinal\":%d,"
        "\"pid\":%ld,\"ppid\":%ld,\"monotonic_ns\":%" PRId64 ",\"rss_kib\":%ld}\n",
        o->nonce,o->ordinal,(long)getpid(),(long)getppid(),stamp,usage.ru_maxrss);
    if(bytes<=0 || bytes>256 || f1_write_all(3,wire,(size_t)bytes) ||
       f1_read_frame(4,reply,&n) || f1_object(reply,n,fields,8,&count) || count!=8)f1_child_error(1,EPROTO);
    ack_time=f1_lookup(fields,count,"monotonic_ns");
    if(!f1_is_number(fields,count,"v",1) || !f1_is_text(fields,count,"phase","ACK") ||
       !f1_is_text(fields,count,"for_phase","PREEXEC") || !f1_is_text(fields,count,"nonce",o->nonce) ||
       !f1_is_number(fields,count,"ordinal",o->ordinal) || !f1_is_number(fields,count,"child_pid",getpid()) ||
       !f1_is_number(fields,count,"launcher_pid",getppid()) || !ack_time || ack_time->is_string ||
       ack_time->number<stamp || ack_time->number>f1_now())f1_child_error(1,EPROTO);
    snprintf(nonce_env,sizeof(nonce_env),"FE_F1_NONCE=%s",o->nonce);
    snprintf(ordinal_env,sizeof(ordinal_env),"FE_F1_ORDINAL=%d",o->ordinal);
    environment[0]=(char *)"LC_ALL=C";environment[1]=(char *)"TZ=UTC";
    environment[2]=(char *)"ASAN_OPTIONS=detect_leaks=1:abort_on_error=1";
    environment[3]=(char *)"UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1";
    environment[4]=nonce_env;environment[5]=ordinal_env;
    environment[6]=(char *)"FE_F1_CONTROL_FD=3";environment[7]=(char *)"FE_F1_ACK_FD=4";environment[8]=NULL;
    /* The launcher's own pipe-error handling must not change target semantics:
     * ignored dispositions survive exec, unlike caught signal handlers. */
    if(signal(SIGPIPE,SIG_DFL)==SIG_ERR)f1_child_error(1,errno);
    execve(o->target[0],o->target,environment);
    f1_child_error(2,errno);
}

static int f1_rusage(struct f1_buffer *b, const struct rusage *r) {
    f1_append(b,"{\"ru_utime_sec\":%jd,\"ru_utime_usec\":%jd,\"ru_stime_sec\":%jd,\"ru_stime_usec\":%jd,"
        "\"ru_maxrss\":%ld,\"ru_ixrss\":%ld,\"ru_idrss\":%ld,\"ru_isrss\":%ld,"
        "\"ru_minflt\":%ld,\"ru_majflt\":%ld,\"ru_nswap\":%ld,\"ru_inblock\":%ld,"
        "\"ru_oublock\":%ld,\"ru_msgsnd\":%ld,\"ru_msgrcv\":%ld,\"ru_nsignals\":%ld,"
        "\"ru_nvcsw\":%ld,\"ru_nivcsw\":%ld}",
        (intmax_t)r->ru_utime.tv_sec,(intmax_t)r->ru_utime.tv_usec,(intmax_t)r->ru_stime.tv_sec,(intmax_t)r->ru_stime.tv_usec,
        r->ru_maxrss,r->ru_ixrss,r->ru_idrss,r->ru_isrss,r->ru_minflt,r->ru_majflt,r->ru_nswap,
        r->ru_inblock,r->ru_oublock,r->ru_msgsnd,r->ru_msgrcv,r->ru_nsignals,r->ru_nvcsw,r->ru_nivcsw);
    return b->bad?-1:0;
}

static int f1_wait_record(struct f1_state *s) {
    char raw[4097];struct f1_buffer b={raw,sizeof(raw),0,0};
    const char *kind=s->reaped?(WIFEXITED(s->wait_status)?"exit":WIFSIGNALED(s->wait_status)?"signal":"other"):"unreaped";
    f1_append(&b,"{\"schema_version\":1,\"nonce\":\"%s\",\"ordinal\":%d,\"case_binding_sha256\":\"%s\","
        "\"launcher_pid\":%ld,\"fork_returned_pid\":%ld,\"pid\":%ld,\"start_ticks\":",
        s->option.nonce,s->option.ordinal,s->option.binding,(long)getpid(),(long)s->child,(long)s->child);
    if(s->start_ticks>=0)f1_append(&b,"%" PRId64,s->start_ticks);else f1_append(&b,"null");
    f1_append(&b,",\"wait4_requested_pid\":%ld,\"wait4_returned_pid\":",(long)s->child);
    if(s->reaped)f1_append(&b,"%ld",(long)s->waited);else f1_append(&b,"null");
    f1_append(&b,",\"raw_wait_status\":");if(s->reaped)f1_append(&b,"%d",s->wait_status);else f1_append(&b,"null");
    f1_append(&b,",\"decoded_exit_kind\":\"%s\",\"exit_code\":",kind);
    if(s->reaped && WIFEXITED(s->wait_status))f1_append(&b,"%d",WEXITSTATUS(s->wait_status));else f1_append(&b,"null");
    f1_append(&b,",\"signal_number\":");
    if(s->reaped && WIFSIGNALED(s->wait_status))f1_append(&b,"%d",WTERMSIG(s->wait_status));else f1_append(&b,"null");
    f1_append(&b,",\"core_dumped\":%s,\"rusage\":",s->reaped&&WIFSIGNALED(s->wait_status)&&WCOREDUMP(s->wait_status)?"true":"false");
    if(s->reaped)(void)f1_rusage(&b,&s->usage);else f1_append(&b,"null");
    f1_append(&b,",\"rusage_origin\":\"native launcher wait4 return for exactly fork_returned_pid\","
        "\"fork_started_monotonic_ns\":%" PRId64 ",\"fork_returned_monotonic_ns\":%" PRId64 ","
        "\"wait_started_monotonic_ns\":%" PRId64 ",\"wait_finished_monotonic_ns\":",
        s->fork_before,s->fork_after,s->wait_before);
    if(s->reaped)f1_append(&b,"%" PRId64,s->wait_after);else f1_append(&b,"null");
    f1_append(&b,",\"exec_error\":");
    if(s->exec_bytes) {
        size_t i;f1_append(&b,"{\"stage\":%d,\"errno\":%d,\"raw_pipe_bytes_hex\":\"",s->exec_stage,s->exec_errno);
        for(i=0;i<s->exec_bytes;++i)f1_append(&b,"%02x",s->exec_raw[i]);
        f1_append(&b,"\"}");
    } else f1_append(&b,"null");
    f1_append(&b,",\"complete_original\":%s}\n",s->reaped?"true":"false");
    return b.bad?-1:f1_member(s,"target-wait.json",b.raw,b.used,4096);
}

static void f1_close(int *fd) { if(*fd>=0){(void)close(*fd);*fd=-1;} }

int main(int argc, char **argv) {
    struct f1_state s;
    struct stat own_identity;
    int cp[2]={-1,-1},ap[2]={-1,-1},ep[2]={-1,-1},op[2]={-1,-1};
    int parent=-1,input=-1,index,failed=0;
    int64_t now;
    static const char *phases[3]={"PREEXEC","ENTRY","RETURN"};
    memset(&s,0,sizeof(s));
    s.directory=s.diagnostic=s.target_log=s.control=s.ack=s.error_pipe=s.output_pipe=-1;
    s.start_ticks=-1;
    if(f1_options(argc,argv,&s.option)) { fputs("F1R1_LAUNCHER_ARGUMENTS_REJECTED\n",stderr);return 2; }
    /* This program owns no provider token. The exec environment is rebuilt from
     * exactly the eight frozen runtime names; all unregistered FDs close. */
    if(signal(SIGPIPE,SIG_IGN)==SIG_ERR)return 2;
    for(index=0;index<3;++index)if(fcntl(index,F_GETFD)<0)return 2;
    s.directory=open(s.option.directory,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(s.directory<0)return 2;
    s.diagnostic=openat(s.directory,"launcher.log",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    parent=openat(s.directory,"..",O_RDONLY|O_DIRECTORY|O_CLOEXEC);
    if(parent<0 || s.diagnostic<0){failed=1;goto finish;}
    s.target_log=openat(parent,"target.log",O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    input=open("/dev/null",O_RDONLY|O_CLOEXEC);
    if(s.target_log<0 || input<0 || pipe2(cp,O_CLOEXEC) || pipe2(ap,O_CLOEXEC) ||
       pipe2(ep,O_CLOEXEC) || pipe2(op,O_CLOEXEC)){f1_fail(&s,"F1R1_LAUNCHER_SETUP_FAILED");failed=1;goto finish;}
    if(f1_executable_hash("/proc/self/exe",s.self_hash,&own_identity,s.option.work_deadline)) {
        f1_fail(&s,"F1R1_LAUNCHER_IMAGE_IDENTITY");failed=1;goto finish;
    }
    s.fork_before=f1_now();
    if(s.fork_before>=s.option.work_deadline){f1_fail(&s,"F1R1_INVOCATION_ADMISSION_EXPIRED");failed=1;goto finish;}
    s.child=fork();s.fork_after=f1_now();
    if(s.child<0){f1_fail(&s,"F1R1_FORK_FAILED");failed=1;goto finish;}
    if(s.child==0)f1_child(&s.option,cp[1],ap[0],ep[1],op[1],input);
    f1_close(&cp[1]);f1_close(&ap[0]);f1_close(&ep[1]);f1_close(&op[1]);f1_close(&input);
    s.control=cp[0];cp[0]=-1;s.ack=ap[1];ap[1]=-1;
    s.error_pipe=ep[0];ep[0]=-1;s.output_pipe=op[0];op[0]=-1;
    if(f1_nonblocking(s.control)||f1_nonblocking(s.error_pipe)||f1_nonblocking(s.output_pipe))f1_fail(&s,"F1R1_LAUNCHER_SETUP_FAILED");
    for(index=0;index<3 && !s.reason;++index) {
        char wire[257],ack[257];size_t bytes=0;int ack_bytes;
        int64_t received,deadline,sent;
        s.phase=phases[index];
        if(f1_frame(&s,wire,&bytes,index)) {
            if(bytes)(void)f1_transcript(&s,index*2+1,"CHILD_TO_LAUNCHER",s.phase,wire,bytes,f1_now(),0);
            break;
        }
        received=f1_now();
        if(f1_transcript(&s,index*2+1,"CHILD_TO_LAUNCHER",s.phase,wire,bytes,received,0)) { f1_fail(&s,"F1R1_TRANSCRIPT_BYTES_OR_WRITE_LIMIT");break; }
        if(f1_validate_message(&s,wire,bytes,s.phase,received)){f1_fail(&s,"F1R1_WIRE_IDENTITY_OR_SCHEMA");break;}
        deadline=received+F1_CHECKPOINT_NS;if(deadline>s.option.work_deadline)deadline=s.option.work_deadline;
        if(f1_snapshot(&s,s.phase,deadline)){f1_fail(&s,"F1R1_PROC_OBSERVATION_FAILED");break;}
        sent=f1_now();
        ack_bytes=snprintf(ack,sizeof(ack),
            "{\"v\":1,\"phase\":\"ACK\",\"for_phase\":\"%s\",\"nonce\":\"%s\",\"ordinal\":%d,"
            "\"child_pid\":%ld,\"launcher_pid\":%ld,\"monotonic_ns\":%" PRId64 "}\n",
            s.phase,s.option.nonce,s.option.ordinal,(long)s.child,(long)getpid(),sent);
        if(sent>deadline || ack_bytes<=0 || ack_bytes>256 ||
           f1_write_all(s.ack,ack,(size_t)ack_bytes) ||
           f1_transcript(&s,index*2+2,"LAUNCHER_TO_CHILD",s.phase,ack,(size_t)ack_bytes,sent,1)) {
            f1_fail(&s,"F1R1_ACK_WRITE_OR_DEADLINE");break;
        }
        ++s.completed_phases;
        s.last_ack_time=sent;
        f1_log(&s,"CHECKPOINT_CAPTURED_AND_ACKED",s.phase);
    }
    while(!s.reason && (!s.reaped || !s.output_eof || !s.error_eof)) {
        f1_drain(&s);
        if(s.reaped && s.output_eof && s.error_eof)break;
        if(f1_now()>=s.option.work_deadline) {
            f1_fail(&s,s.option.engineering?"F1R1_ENGINEERING_INVOCATION_TIMEOUT":"F1R1_SCIENCE_INVOCATION_TIMEOUT");break;
        }
        if(f1_poll(&s,s.option.work_deadline)<0)break;
    }
    if(!s.reason) {
        if(!s.error_eof || s.exec_bytes)f1_fail(&s,s.exec_errno?"F1R1_EXECVE_FAILED":"F1R1_EXEC_ERROR_PIPE_FORMAT");
        else if(!s.reaped || !WIFEXITED(s.wait_status) || WEXITSTATUS(s.wait_status)!=0 || s.returned_code!=0)
            f1_fail(&s,"F1R1_TARGET_NONZERO_EXIT");
        else if(s.completed_phases!=3)f1_fail(&s,"F1R1_CHECKPOINT_REQUIRED");
    }
    if(s.reason && !s.reaped) {
        /* PID cannot be reused while this exact direct child is unreaped. */
        if(kill(s.child,SIGKILL)<0 && errno!=ESRCH)f1_log(&s,"OWNED_SIGKILL_FAILED",s.phase);
    }
    while(!s.reaped && f1_now()<s.option.final_deadline) {
        f1_drain(&s);if(s.reaped)break;
        (void)f1_poll(&s,s.option.final_deadline);
    }
    f1_drain(&s);
    if(!s.reaped)f1_fail(&s,"F1R1_OWNED_CHILD_NOT_REAPED");
    if(f1_wait_record(&s))f1_fail(&s,"F1R1_WAIT_RECORD_BYTES_OR_WRITE_LIMIT");
finish:
    now=f1_now();
    if(now>s.option.final_deadline) {
        f1_log(&s,"FINAL_DEADLINE_EXCEEDED",s.phase);
        if(!s.reason)s.reason="F1R1_FINAL_INVOCATION_DEADLINE";
        failed=1;
    }
    if(s.reason)failed=1;
    if(s.diagnostic>=0)f1_log(&s,failed?"PROTOCOL_REJECTED":"PROTOCOL_ONLY_COMPLETE",s.phase);
    f1_close(&input);f1_close(&parent);
    for(index=0;index<2;++index){f1_close(&cp[index]);f1_close(&ap[index]);f1_close(&ep[index]);f1_close(&op[index]);}
    f1_close(&s.control);f1_close(&s.ack);f1_close(&s.error_pipe);f1_close(&s.output_pipe);
    f1_close(&s.target_log);f1_close(&s.diagnostic);f1_close(&s.directory);
    now=f1_now();if(now>s.option.final_deadline)failed=1;
    if(printf("{\"kind\":\"F1_NATIVE_PROTOCOL_ONLY\",\"reason\":\"%s\",\"child_pid\":%ld,"
           "\"owned_child_reaped\":%s,\"completed_phases\":%d,\"final_deadline_exceeded\":%s,"
           "\"overflow_member\":\"%s\",\"observed_bytes\":%zu,\"retained_bytes\":%zu}\n",
           s.reason?s.reason:(failed?"F1R1_LAUNCHER_FAILURE":"PROTOCOL_ONLY_COMPLETE"),(long)s.child,
           s.reaped?"true":"false",s.completed_phases,now>s.option.final_deadline?"true":"false",
           s.overflow_member?s.overflow_member:"",s.observed_bytes,s.retained_bytes)<0)failed=1;
    if(fflush(stdout)==EOF)failed=1;
    /* Final serialization/flush is work too. The outer collector independently
     * checks its owned launcher wait4 and complete evidence encoding deadline. */
    if(f1_now()>s.option.final_deadline)failed=1;
    return failed?2:0;
}
