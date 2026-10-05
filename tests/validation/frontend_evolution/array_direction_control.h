#ifndef FE_ARRAY_DIRECTION_CONTROL_H
#define FE_ARRAY_DIRECTION_CONTROL_H
#include "array_native.h"
/* First-party, fixed-policy research control. No direction estimation. Confidence
 * and speech/render flags are supplied externally; they are not calibrated by us.
 * Caller serializes all calls and resets this controller with the array lifecycle.
 */
typedef struct {
    uint64_t sample_index; /* Audio sample-frame end boundary, same clock as array. */
    double direction[3], confidence;
    uint32_t near_speech, render_active; /* Exactly 0 or 1. */
} fe_direction_observation;
typedef struct {
    uint64_t last_audio, last_observation, first_stable, cooldown_until;
    double anchor[3];
    uint32_t seen, coherent_count;
    uint64_t accepted;
} fe_direction_control;
typedef enum {
    FE_DIRECTION_ACCEPTED = 0,
    FE_DIRECTION_HOLD = 1,
    FE_DIRECTION_COOLDOWN = 2,
    FE_DIRECTION_BUSY = 3,
    FE_DIRECTION_INVALID = -1,
    FE_DIRECTION_RESET_REQUIRED = -2
} fe_direction_result;
void fe_direction_control_reset(fe_direction_control *control);
/* Fixed policy: confidence>=.8, near speech and no render; 3 observations over
 * >=20ms within 5deg of the FIRST stable direction, >=15deg from committed beam;
 * 200ms cooldown after acceptance; <=20ms observation age and gap; 20ms fade.
 * Future/stale/duplicate/invalid observations leave both objects unchanged.
 * A backwards array clock requires explicit controller reset. Rejected valid
 * speech/confidence/render gates clear stability; no pending observation queue.
 * Reset both controller and array together (reinitialization is not auto-detected).
 */
fe_direction_result fe_direction_control_offer(fe_direction_control *control,
                                                fe_array *array,
                                                const fe_direction_observation *observation);
#endif
