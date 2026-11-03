// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <stdint.h>
#include <stdbool.h>
typedef uint8_t bd_addr_t[6];
typedef void (*btstack_packet_handler_t)(uint8_t,uint16_t,uint8_t *,uint16_t);
#define ERROR_CODE_SUCCESS 0
#define L2CAP_DATA_PACKET 6
#define HCI_EVENT_PACKET 4
#define L2CAP_EVENT_CHANNEL_OPENED 0x70
#define L2CAP_EVENT_CHANNEL_CLOSED 0x71
#define L2CAP_EVENT_CAN_SEND_NOW 0x79
static inline uint8_t hci_event_packet_get_type(const uint8_t *p){return p[0];}
static inline uint16_t mock_cid(const uint8_t*p){return p[2]|(uint16_t)p[3]<<8;}
#define l2cap_event_channel_opened_get_local_cid mock_cid
#define l2cap_event_channel_closed_get_local_cid mock_cid
#define l2cap_event_can_send_now_get_local_cid mock_cid
static inline uint8_t l2cap_event_channel_opened_get_status(const uint8_t*p){return p[4];}
static inline void l2cap_event_channel_opened_get_address(const uint8_t*p,bd_addr_t out){for(int i=0;i<6;i++)out[i]=p[5+i];}
static inline uint16_t l2cap_event_channel_opened_get_remote_mtu(const uint8_t*p){(void)p;return 1691;}
uint32_t btstack_run_loop_get_time_ms(void);
uint8_t l2cap_create_channel(btstack_packet_handler_t,bd_addr_t,uint16_t,uint16_t,uint16_t*);
uint8_t l2cap_send(uint16_t,uint8_t*,uint16_t);
uint8_t l2cap_disconnect(uint16_t);
uint8_t l2cap_request_can_send_now_event(uint16_t);
uint8_t sdp_register_service(const uint8_t*);
