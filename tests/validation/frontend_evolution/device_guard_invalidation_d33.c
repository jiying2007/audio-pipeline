/* D33 research-local previous-primary-frame guard; frozen DSP and output composition. */
#include "activity/ap_activity.h"
#include "device_guard_invalidation_d33.h"
#include "device_dwell_selector_d27.h"
#include "device_transition_d28.h"
#define main d33_unused_d26_main
#include "device_field_d26.c"
#undef main

static int d33_self_test(void) {
    ap_activity_state_t detector;ap_activity_result_t flags;
    uint32_t i,frame;
    if (d33_guard_self_test()) return 30;
    d27_selection_t selection={{0u,0u,0u},0u,0u};d28_transition_t transition={0u,0u,0u,0u};
    for (frame=0u;frame<56u;++frame) {
        int change=d27_choose(&selection,frame,50u,1,1,frame<3u ? 1.0 : .1,frame<3u ? .1 : 1.0);
        if (change!=((frame==2u || frame==54u) ? 1 : 0)) return 10;
        if (change && !d28_begin(&transition,selection.base.bank)) return 11;
        for (i=0u;i<160u;++i) d28_advance(&transition);
        if (transition.remaining!=((frame==2u || frame==54u) ? 160u : 0u) || transition.bank!=selection.base.bank) return 12;
    }
    if (!d28_begin(&transition,1u) || d27_choose(&selection,56u,50u,0,1,1.0,.1)!=0) return 14;
    d28_reset(&transition);
    if (selection.base.bank || selection.has_last || transition.bank || transition.remaining) return 15;
    ap_activity_init(&detector,1e-7f,1.5f,3u);
    ap_activity_process(&detector,1e-8f,1e-4f,&flags);
    if (!flags.far_end_active || flags.double_talk_active) return 20;
    ap_activity_process(&detector,1e-2f,1e-4f,&flags);
    if (!flags.far_end_active || !flags.double_talk_active || detector.double_talk_hangover!=3u) return 21;
    for (i=0u;i<3u;++i) {
        ap_activity_process(&detector,1e-8f,1e-4f,&flags);
        if (detector.double_talk_hangover!=2u-i || flags.double_talk_active!=(uint8_t)(i<2u)) return 22;
    }
    ap_activity_reset(&detector);
    if (detector.smoothed_mic_energy!=0.0f || detector.smoothed_reference_energy!=0.0f ||
        detector.double_talk_hangover || detector.far_end_hangover || detector.hangover_frames!=3u) return 23;
    puts("D33_SELF_TEST_PASS actual-Activity/onset/hangover/reset/frozen-composition");return 0;
}

int main(int argc,char **argv) {
    static const char *names[]={"mic.f32le","reference.f32le","echo.f32le","residual.f32le","primary_echo.f32le",
        "primary_residual.f32le","shadow_echo.f32le","shadow_residual.f32le","state.csv","selector.csv","transition.csv","activity.csv","guard.csv"};
    FILE *inputs[2]={NULL},*files[13]={NULL};uint32_t frames=0u,notify=0u,frame=0u,i,shadow_calls=0u,resets=0u,mixed=0u;
    uint16_t endian=1u;int has_notify,future,feedback,result=0;char path[1024];
    float mic[160],ref[160],pe[160],pr[160],se[160]={0},sr[160]={0},oe[160],out[160];
    d27_selection_t selection={{0u,0u,0u},0u,0u};d28_transition_t transition={0u,0u,0u,0u};ap_activity_state_t detector;d33_guard_t guard_state={0};
    if (argc==2 && strcmp(argv[1],"--self-test")==0) return d33_self_test();
    if (argc!=8) return 2;
    has_notify=strcmp(argv[4],"none")!=0;future=strcmp(argv[6],"future")==0;feedback=strcmp(argv[7],"feedback")==0;
    if (!number(argv[3],&frames) || !frames || (has_notify && (!number(argv[4],&notify) || notify>=frames)) ||
        (!feedback && strcmp(argv[7],"monitor")) || (!future && strcmp(argv[6],"normal")) || (future && !has_notify) ||
        *(const unsigned char *)&endian!=1u || sizeof(float)!=4u) {
        fprintf(stderr,"D33_INVALID_ARGUMENT_REJECT primary_calls=0 shadow_calls=0 activity_calls=0 observer_calls=0\n");return 2;
    }
    for (i=0u;i<2u;++i) {
        inputs[i]=fopen(argv[i+1u],"rb");
        if (!inputs[i] || !length(inputs[i],(long)frames*640L)) { result=4;goto done; }
    }
    for (i=0u;i<13u;++i) {
        int n=snprintf(path,sizeof(path),"%s/%s",argv[5],names[i]);
        if (n<0 || (size_t)n>=sizeof(path)) { result=2;goto done; }
        files[i]=fopen(path,"wb");if (!files[i]) { result=4;goto done; }
    }
    ap_activity_init(&detector,1e-7f,1.5f,3u);ap_aec_backend_init(&primary,160u,1536u,2u);
    if (primary.backend.block!=32u || primary.backend.active_partitions!=48u ||
        fprintf(files[8],"frame,runtime_stride,steady_frames,adapt_phase,constrain_partition,x_head,x_power_total,weight_l2\n")<0 ||
        fprintf(files[9],"frame,active,far,dt,bank,streak,change,primary_energy,shadow_energy,hold_remaining\n")<0 ||
        fprintf(files[10],"frame,active,far,dt,bank,change,remaining_after_frame,alpha_first,alpha_last\n")<0 ||
        fprintf(files[12],"frame,mode,detected_dt,guard,used_dt,armed_before,stable_before,hold_after_gate,cme,cre,ratio,valid_me,valid_re,armed_after,stable_after\n")<0 ||
        fprintf(files[11],"frame,mic_energy,reference_energy,smoothed_mic_energy,smoothed_reference_energy,far_hangover,dt_hangover,far,dt\n")<0) { result=5;goto done; }
    for (frame=0u;frame<frames;++frame) {
        ap_activity_result_t gates;int active=has_notify && frame>=notify,change;uint32_t part,bin;
        float mic_energy=1e-12f,ref_energy=1e-12f;uint8_t detected_dt;
        uint32_t armed_before,stable_before;int guard;
        double p_energy=0.0,s_energy=0.0,weight=0.0,first=1.0,last=1.0;ap_aec_result_t primary_result;
        d33_invalidate(&guard_state,feedback,has_notify && frame==notify);
        armed_before=guard_state.armed;stable_before=guard_state.stable;
        if (fread(mic,sizeof(float),160u,inputs[0])!=160u || fread(ref,sizeof(float),160u,inputs[1])!=160u) { result=4;goto done; }
        for (i=0u;i<160u;++i) {
            if (!isfinite(mic[i]) || !isfinite(ref[i])) { result=7;goto done; }
            if (future && frame>=notify) { mic[i]=-mic[i];ref[i]=-ref[i]; }
            mic_energy+=mic[i]*mic[i];ref_energy+=ref[i]*ref[i];
        }
        mic_energy/=160.0f;ref_energy/=160.0f;
        ap_activity_process(&detector,mic_energy,ref_energy,&gates);
        detected_dt=gates.double_talk_active;guard=d33_gate(&guard_state,gates.far_end_active);
        if (feedback && guard) gates.double_talk_active=1u;
        if (has_notify && frame==notify) { shadow=primary;ap_aec_backend_reset(&shadow);++resets; }
        ap_aec_backend_process(&primary,1,.22f,160u,mic,ref,pr,pe,gates.far_end_active,gates.double_talk_active,&primary_result);
        if (active) {
            ap_aec_result_t shadow_result;++shadow_calls;
            ap_aec_backend_process(&shadow,1,.22f,160u,mic,ref,sr,se,gates.far_end_active,gates.double_talk_active,&shadow_result);
            if (!isfinite(shadow_result.echo_energy)) { result=6;goto done; }
        }
        for (i=0u;i<160u;++i) {
            double p=(double)pr[i],s=(double)sr[i];p_energy+=p*p;s_energy+=s*s;
            if (!isfinite(pe[i]) || !isfinite(pr[i]) || !isfinite(se[i]) || !isfinite(sr[i]) ||
                fabsf(mic[i]-(pe[i]+pr[i]))>1e-6f || (active && fabsf(mic[i]-(se[i]+sr[i]))>1e-6f)) { result=7;goto done; }
        }
        change=d27_choose(&selection,frame,50u,active,gates.far_end_active && !gates.double_talk_active,p_energy,s_energy);
        if (change<0 || sync_calls || !isfinite(primary_result.echo_energy) || !isfinite(primary.backend.x_power_total) ||
            primary.runtime_adapt_stride!=2u || primary.backend.adapt_phase>1u) { result=6;goto done; }
        if (!active) d28_reset(&transition);
        else if (change && !d28_begin(&transition,selection.base.bank)) { result=7;goto done; }
        if (transition.bank!=selection.base.bank) { result=7;goto done; }
        for (i=0u;i<160u;++i) {
            double alpha=d28_alpha(&transition);const float *e=selection.base.bank ? se : pe,*r=selection.base.bank ? sr : pr;
            const float *old_e=transition.from_bank ? se : pe,*old_r=transition.from_bank ? sr : pr;
            if (!i) first=alpha;
            last=alpha;oe[i]=transition.remaining ? d28_mix(old_e[i],e[i],alpha) : e[i];
            out[i]=transition.remaining ? d28_mix(old_r[i],r[i],alpha) : r[i];
            if (!isfinite(oe[i]) || !isfinite(out[i]) || fabsf(mic[i]-(oe[i]+out[i]))>1e-6f) { result=7;goto done; }
            if (transition.remaining) ++mixed;
            d28_advance(&transition);
        }
        if (!d33_observe(&guard_state,mic,pe,pr,gates.far_end_active,detected_dt)) { result=7;goto done; }
        for (part=0u;part<primary.backend.active_partitions;++part) for (bin=0u;bin<primary.backend.bins;++bin) {
            double re=(double)primary.backend.weights[part][bin].re,im=(double)primary.backend.weights[part][bin].im;weight+=re*re+im*im;
        }
        if (!isfinite(weight) || !isfinite(mic_energy) || !isfinite(ref_energy)) { result=7;goto done; }
        {
            const float *traces[]={mic,ref,oe,out,pe,pr,se,sr};
            for (i=0u;i<8u;++i) if (fwrite(traces[i],sizeof(float),160u,files[i])!=160u) { result=8;goto done; }
        }
        if (fprintf(files[8],"%u,%u,%u,%u,%u,%u,%.9g,%.17g\n",frame,primary.runtime_adapt_stride,primary.steady_frames,
            primary.backend.adapt_phase,primary.backend.constrain_partition,primary.backend.x_head,(double)primary.backend.x_power_total,weight)<0 ||
            fprintf(files[9],"%u,%d,%u,%u,%u,%u,%d,%.17g,%.17g,%u\n",frame,active,(unsigned)gates.far_end_active,(unsigned)gates.double_talk_active,selection.base.bank,
            selection.base.streak,change,p_energy,s_energy,active ? d27_remaining(&selection,frame,50u) : 0u)<0 ||
            fprintf(files[10],"%u,%d,%u,%u,%u,%d,%u,%.17g,%.17g\n",frame,active,(unsigned)gates.far_end_active,(unsigned)gates.double_talk_active,selection.base.bank,
            change,transition.remaining,first,last)<0 ||
            fprintf(files[11],"%u,%.9g,%.9g,%.9g,%.9g,%u,%u,%u,%u\n",frame,(double)mic_energy,(double)ref_energy,
            (double)detector.smoothed_mic_energy,(double)detector.smoothed_reference_energy,detector.far_end_hangover,detector.double_talk_hangover,
            (unsigned)gates.far_end_active,(unsigned)detected_dt)<0 ||
            fprintf(files[12],"%u,%d,%u,%d,%u,%u,%u,%u,%.17g,%.17g,%.17g,%u,%u,%u,%u\n",frame,feedback,(unsigned)detected_dt,guard,(unsigned)gates.double_talk_active,
            armed_before,stable_before,guard_state.hold,guard_state.cme,guard_state.cre,guard_state.ratio,(unsigned)guard_state.valid_me,(unsigned)guard_state.valid_re,
            guard_state.armed,guard_state.stable)<0) { result=8;goto done; }
    }
done:
    for (i=0u;i<2u;++i) if (inputs[i] && fclose(inputs[i])) result=9;
    for (i=0u;i<13u;++i) if (files[i] && fclose(files[i])) result=9;
    if (!result) {
        size_t buffers=sizeof(mic)+sizeof(ref)+sizeof(pe)+sizeof(pr)+sizeof(se)+sizeof(sr)+sizeof(oe)+sizeof(out);
        printf("{\"frames\":%u,\"samples\":%u,\"primary_calls\":%u,\"shadow_calls\":%u,\"shadow_reset_calls\":%u,\"selector_calls\":%u,\"transition_calls\":%u,\"mixed_samples\":%u,\"remaining\":%u,\"switch_count\":%u,\"sync_calls\":%llu,\"aec_state_bytes\":%zu,\"two_aec_state_bytes\":%zu,\"selector_state_bytes\":%zu,\"transition_state_bytes\":%zu,\"frame_buffer_bytes\":%zu,\"scoped_bytes\":%zu,\"activity_calls\":%u,\"activity_state_bytes\":%zu,\"observer_calls\":%u,\"guard_state_bytes\":%zu}\n",
            frames,frames*160u,frame,shadow_calls,resets,frame,frame,mixed,transition.remaining,selection.base.changes,(unsigned long long)sync_calls,
            sizeof(primary),sizeof(primary)+sizeof(shadow),sizeof(selection),sizeof(transition),buffers,
            sizeof(primary)+sizeof(shadow)+sizeof(selection)+sizeof(transition)+buffers+sizeof(detector)+sizeof(guard_state),frame,sizeof(detector),frame,sizeof(guard_state));
    }
    return result;
}

