// SPDX-License-Identifier: GPL-3.0-only
// One owner serializes requests, peer responses and main-loop rebuild results.
// No SDK dependency: production adapters execute the returned actions.
#include "eld_transition.h"
#include <string.h>
void eld_transition_reset(eld_transition *s){memset(s,0,sizeof(*s));}
void eld_transition_configured(eld_transition *s) {
 *s=(eld_transition){.phase=ELD_WAIT_START,.requested=1,.built=1};
}
bool eld_transition_busy(const eld_transition *s) {
 return s->managed && s->phase!=ELD_READY && s->phase!=ELD_OFF;
}
unsigned eld_transition_request(eld_transition *s,bool streaming) {
 if(s->phase==ELD_OFF || s->phase==ELD_FAILED)return ELD_NOTHING;
 s->requested++;s->managed=true;
 if(s->phase==ELD_WAIT_START || s->phase==ELD_WAIT_SUSPEND || s->phase==ELD_REBUILD)
   return ELD_STOP; /* Latest settings win; never duplicate an in-flight command. */
 s->phase=streaming?ELD_WAIT_SUSPEND:ELD_REBUILD;
 return ELD_STOP|(streaming?ELD_SUSPEND:ELD_BUILD);
}
unsigned eld_transition_suspended(eld_transition *s) {
 if(s->phase==ELD_WAIT_SUSPEND){s->phase=ELD_REBUILD;return ELD_BUILD;}
 if(s->phase==ELD_WAIT_START && s->managed) {
   /* Our managed rebuild's START is still outstanding when the peer's
      SUSPEND is accepted (a late/duplicate accept or an early peer suspend).
      Cancel that START into one bounded rebuild, matching the unmanaged
      early-START cancellation, instead of idling until the 3 s deadline
      aborts the transition and drops the ACL. */
   s->start_inflight=false;s->phase=ELD_REBUILD;
   return ELD_STOP|ELD_BUILD;
 }
 if(s->phase==ELD_READY || (s->phase==ELD_WAIT_START && !s->managed)) {
   s->phase=ELD_READY;s->start_inflight=false;
   return eld_transition_request(s,false);
 }
 return ELD_NOTHING;
}
unsigned eld_transition_started(eld_transition *s) {
 if(s->phase!=ELD_WAIT_START)return ELD_NOTHING;
 s->start_inflight=false;
 if(s->requested!=s->built) {
   s->phase=ELD_WAIT_SUSPEND;s->managed=true;
   return ELD_STOP|ELD_SUSPEND;
 }
 s->phase=ELD_READY;s->managed=false;
 return ELD_RUN|ELD_SETTLE;
}
unsigned eld_transition_built(eld_transition *s,bool success) {
 if(s->phase!=ELD_REBUILD)return ELD_NOTHING;
 if(!success)return eld_transition_failed(s);
 s->built=s->requested;s->phase=ELD_WAIT_START;s->start_inflight=false;
 return ELD_START;
}
unsigned eld_transition_failed(eld_transition *s) {
 if(s->phase==ELD_OFF || s->phase==ELD_FAILED)return ELD_NOTHING;
 s->phase=ELD_FAILED;s->managed=true;s->start_inflight=false;
 return ELD_STOP|ELD_DROP;
}
unsigned eld_transition_rejected(eld_transition *s) {
 if(eld_transition_busy(s))return eld_transition_failed(s);
 if(s->phase==ELD_WAIT_START){s->phase=ELD_READY;s->start_inflight=false;}
 return ELD_NOTHING; /* Normal startup/resume retains the existing retry policy. */
}
bool eld_transition_begin_start(eld_transition *s) {
 if(s->phase==ELD_READY)s->phase=ELD_WAIT_START;
 if(s->phase!=ELD_WAIT_START || s->start_inflight)return false;
 s->start_inflight=true;return true;
}
const char *eld_transition_phase_name(eld_phase phase) {
 switch(phase) {
 case ELD_OFF:return "off";case ELD_READY:return "ready";
 case ELD_WAIT_SUSPEND:return "wait-suspend";case ELD_REBUILD:return "rebuild";
 case ELD_WAIT_START:return "wait-start";case ELD_FAILED:return "failed";
 default:return "invalid";
 }
}
