// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include "aacenc_lib.h"
#include "eld_profile.h"
/* Caller owns its context lock. Existing encoder is closed before allocating
 * the next one; any failure leaves a NULL handle and cleared stream info. */
AACENC_ERROR eld_encoder_open(HANDLE_AACENCODER*,AACENC_InfoStruct*,const eld_profile*);
