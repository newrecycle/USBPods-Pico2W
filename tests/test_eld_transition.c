// SPDX-License-Identifier: GPL-3.0-only
#include "eld_transition.h"
#include <assert.h>
#include <stdio.h>
static eld_transition state;
static void ready(void) {
 eld_transition_configured(&state);
 assert(eld_transition_begin_start(&state));
 assert(!eld_transition_begin_start(&state));
 assert(eld_transition_started(&state)==(ELD_RUN|ELD_SETTLE));
 assert(state.phase==ELD_READY && !eld_transition_busy(&state));
}
int main(void) {
 eld_transition_reset(&state);assert(!eld_transition_request(&state,true));
 ready();assert(eld_transition_request(&state,true)==(ELD_STOP|ELD_SUSPEND));
 assert(!eld_transition_built(&state,true)); // Cannot rebuild before suspend ACK.
 assert(!eld_transition_started(&state)); // Stale START cannot resume the pump.
 assert(eld_transition_request(&state,true)==ELD_STOP); // Coalesce latest setting.
 assert(eld_transition_suspended(&state)==ELD_BUILD);
 assert(eld_transition_request(&state,false)==ELD_STOP);
 assert(eld_transition_built(&state,true)==ELD_START);
 assert(state.built==state.requested && eld_transition_begin_start(&state));
 assert(eld_transition_started(&state)==(ELD_RUN|ELD_SETTLE));
 assert(!eld_transition_started(&state)); // Duplicate ACK has no pump side effect.

 // A setting arriving during START waits for its ACK, then suspends once.
 assert(eld_transition_request(&state,true)==(ELD_STOP|ELD_SUSPEND));
 assert(eld_transition_suspended(&state)==ELD_BUILD);
 assert(eld_transition_built(&state,true)==ELD_START);
 assert(eld_transition_begin_start(&state));
 assert(eld_transition_request(&state,false)==ELD_STOP);
 assert(eld_transition_started(&state)==(ELD_STOP|ELD_SUSPEND));
 assert(eld_transition_suspended(&state)==ELD_BUILD);
 assert(eld_transition_built(&state,true)==ELD_START);
 assert(eld_transition_begin_start(&state));
 assert(eld_transition_started(&state)==(ELD_RUN|ELD_SETTLE));

 // A request before initial START must not emit an extra START or hot rebuild.
 eld_transition_configured(&state);
 assert(eld_transition_request(&state,false)==ELD_STOP);
 assert(!eld_transition_built(&state,true));
 assert(eld_transition_begin_start(&state));
 assert(eld_transition_started(&state)==(ELD_STOP|ELD_SUSPEND));

 // Allocation/configuration failure or signaling rejection fails closed once.
 for(unsigned failure=0;failure<3;failure++) {
   ready();eld_transition_request(&state,true);
   unsigned action;
   if(failure==0){eld_transition_suspended(&state);action=eld_transition_built(&state,false);}
   else if(failure==1)action=eld_transition_rejected(&state);
   else {eld_transition_suspended(&state);eld_transition_built(&state,true);action=eld_transition_rejected(&state);}
   assert(action==(ELD_STOP|ELD_DROP) && state.phase==ELD_FAILED);
   assert(!eld_transition_failed(&state) && !eld_transition_started(&state));
   assert(!eld_transition_request(&state,true) && !eld_transition_begin_start(&state));
   eld_transition_reset(&state);assert(!eld_transition_built(&state,true));
 }
 ready();assert(eld_transition_suspended(&state)==(ELD_STOP|ELD_BUILD));
 assert(eld_transition_built(&state,true)==ELD_START);
 eld_transition_reset(&state);assert(!eld_transition_started(&state));
 // Retry exactly one unanswered managed START, never initial OPEN/START,
 // failure, another phase, or a second request in the same built revision.
 eld_transition_configured(&state);assert(eld_transition_begin_start(&state));
 assert(!eld_transition_retry_start(&state));
 ready();eld_transition_request(&state,true);eld_transition_suspended(&state);
 eld_transition_built(&state,true);assert(eld_transition_begin_start(&state));
 assert(eld_transition_retry_start(&state)==ELD_START && state.start_retries==1);
 assert(eld_transition_begin_start(&state));
 eld_transition_request(&state,false);assert(!eld_transition_retry_start(&state));
 assert(eld_transition_started(&state)==(ELD_STOP|ELD_SUSPEND));
 eld_transition_failed(&state);assert(!eld_transition_retry_start(&state));
 puts("ELD transition ordering, superseded requests, stale events and failure actions passed");
}
