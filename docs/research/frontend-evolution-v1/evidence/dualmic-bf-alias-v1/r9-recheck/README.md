# Corrected R9 source host recheck

Executed on 2026-11-10 with GCC 14.2.0 against corrected proposal 1e633c01404767a71b398ec2b44ddef8ee5b2383. BF SHA256: 4e6370504effc76ff3334ecb08e7d1ad2deb408586fa5165d997ae965f244246. The only production-source difference from the original proposal is removal of one terminal LF. Original logs remain unchanged.

Internal test: tests/test_beamformer_alias.c with corrected src/frontend/ap_beamformer.c, -std=c11 -Wall -Wextra -Werror -I src -lm; three builds: -O2, -O2 -ffast-math, and -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer. Each executed 12,240 frames with zero mismatches. Sanitizer execution used ASAN_OPTIONS=detect_leaks=0, retaining the previously disclosed ptrace limitation.

Public wrapper: use the unchanged sibling public-wrapper/test.c and minimal configuration header, src/modules/ap_beamformer_module.c, and corrected BF source. Flags: -std=c11 -Wall -Wextra -Werror -I public-wrapper -I include -I src -lm; builds -O2, -O2 -DAP_BUILD_BF_DIRECTION_TRACKING=0, and the same sanitizer flags above. Each executed 1,440 calls with zero failures. Disabled tracking includes 720 successful calls and 720 AP_ESTATE no-mutation checks. Source/test paths refer to the repository layout; public-wrapper is the sibling evidence directory.

These are targeted actual host regressions, not full CMake, ARM, acoustic quality, current remote-head CI, or fresh-main qualification. Initial-route rather than persistent-route coverage applies as described in the original report.
