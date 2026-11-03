// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef struct { uint8_t id,value; bool status; } control_command;
typedef struct { char line[32]; uint8_t length; bool active,overflow; } control_input;
enum control_result { CONTROL_BYPASS,CONTROL_WAIT,CONTROL_READY,CONTROL_INVALID };
/* Colon-prefixed lines share the existing console with legacy single keys. */
enum control_result control_input_feed(control_input *,char,control_command *);
