/* SPDX-License-Identifier: GPL-3.0-only
 * Bounded HFP-AG connection probe. No USB microphone or audio-quality claim.
 */
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/cyw43_arch.h"
#include "btstack.h"

uint32_t usbpods_flushable_tx_count; /* required by the USBPods SDK patch */
static btstack_packet_callback_registration_t registration;
static btstack_timer_source_t deadline;
static hci_con_handle_t acl = HCI_CON_HANDLE_INVALID;
static hci_con_handle_t sco = HCI_CON_HANDLE_INVALID;
static uint8_t record[256];
static unsigned sco_packets;
static const char *phase = "boot";
static char command[40];
static unsigned command_len;
static const uint8_t codecs[] = {HFP_CODEC_CVSD};
static const hfp_ag_indicator_t indicators[] = {
    {1,"service",0,1,0,0,0,0}, {2,"call",0,1,0,1,1,0},
    {3,"callsetup",0,3,0,1,1,0}, {4,"battchg",0,5,5,0,0,0},
    {5,"signal",0,5,0,0,1,0}, {6,"roam",0,1,0,0,1,0},
    {7,"callheld",0,2,0,1,1,0}
};
static void timeout(btstack_timer_source_t *timer) {
    (void)timer;
    printf("RESULT TIMEOUT phase=%s acl=%04x sco=%04x; unplug/replug before retry\n",
           phase, acl, sco);
    /* Do not turn a missing asynchronous completion into a successful result.
     * Disconnect is best effort: the documented controller wedge can prevent it.
     */
    if (acl != HCI_CON_HANDLE_INVALID) gap_disconnect(acl);
    phase = "timeout";
}
static void arm(const char *next, unsigned ms) {
    phase = next;
    btstack_run_loop_remove_timer(&deadline);
    btstack_run_loop_set_timer_handler(&deadline, timeout);
    btstack_run_loop_set_timer(&deadline, ms);
    btstack_run_loop_add_timer(&deadline);
}
static void help(void) {
    printf("\nUSBPods SCO PROBE: diagnostic only; CVSD; no microphone forwarding\n"
           "s = scan; c AA:BB:CC:DD:EE:FF = connect headset; a = request SCO\n"
           "d = disconnect; ? = status. Put headset into pairing mode first.\n");
    printf("STATUS phase=%s acl=%04x sco=%04x rx_packets=%u\n",phase,acl,sco,sco_packets);
}
static void execute(void) {
    bd_addr_t peer;
    if (!strcmp(command,"s")) {
        printf("SCAN\n"); gap_inquiry_start(5);
    } else if (!strncmp(command,"c ",2) && strlen(command+2)==17 &&
               sscanf_bd_addr(command+2,peer)) {
        if (acl != HCI_CON_HANDLE_INVALID) { printf("Disconnect first\n"); return; }
        arm("service-level",15000);
        uint8_t status=hfp_ag_establish_service_level_connection(peer);
        printf("SLC_REQUEST status=%02x\n",status);
        if (status) { btstack_run_loop_remove_timer(&deadline); phase="slc-rejected"; }
    } else if (!strcmp(command,"a")) {
        if (acl == HCI_CON_HANDLE_INVALID || sco != HCI_CON_HANDLE_INVALID) {
            printf("Need an HFP service-level connection without SCO\n"); return;
        }
        arm("sco",10000);
        uint8_t status=hfp_ag_establish_audio_connection(acl);
        printf("SCO_REQUEST status=%02x; command acceptance is not completion\n",status);
        if (status) { btstack_run_loop_remove_timer(&deadline); phase="sco-rejected"; }
    } else if (!strcmp(command,"d")) {
        if (acl != HCI_CON_HANDLE_INVALID) gap_disconnect(acl);
    } else help();
}
static void input(char c) {
    if (c=='\r' || c=='\n') {
        if (command_len) { command[command_len]=0; execute(); command_len=0; }
    } else if (c==8 || c==127) {
        if (command_len) --command_len;
    } else if (c>=32 && c<127) {
        if (command_len < sizeof(command)-1) command[command_len++]=c;
        else { command_len=0; printf("Command too long\n"); }
    }
}
static void packet(uint8_t type,uint16_t channel,uint8_t *event,uint16_t size) {
    (void)channel;
    if (type==HCI_SCO_DATA_PACKET) {
        if (size>=3 && little_endian_read_16(event,0)%4096==sco) {
            ++sco_packets;
            if (sco_packets==1) printf("SCO_RX first packet; audio not validated\n");
        }
        return;
    }
    if (type!=HCI_EVENT_PACKET) return;
    switch (hci_event_packet_get_type(event)) {
    case BTSTACK_EVENT_STATE:
        if (btstack_event_state_get_state(event)==HCI_STATE_WORKING) {
            btstack_run_loop_remove_timer(&deadline); phase="ready"; help();
        }
        break;
    case HCI_EVENT_PIN_CODE_REQUEST: {
        bd_addr_t peer; hci_event_pin_code_request_get_bd_addr(event,peer);
        gap_pin_code_response(peer,"0000"); break;
    }
    case GAP_EVENT_INQUIRY_RESULT: {
        bd_addr_t peer; gap_event_inquiry_result_get_bd_addr(event,peer);
        printf("FOUND %s\n",bd_addr_to_str(peer)); break;
    }
    case HCI_EVENT_SYNCHRONOUS_CONNECTION_COMPLETE:
        printf("RAW_SYNCHRONOUS_COMPLETE status=%02x\n",event[2]); break;
    case HCI_EVENT_DISCONNECTION_COMPLETE:
        if (hci_event_disconnection_complete_get_connection_handle(event)==acl) {
            acl=HCI_CON_HANDLE_INVALID; sco=HCI_CON_HANDLE_INVALID;
            btstack_run_loop_remove_timer(&deadline); phase="disconnected";
        }
        break;
    case HCI_EVENT_HFP_META:
        switch (hci_event_hfp_meta_get_subevent_code(event)) {
        case HFP_SUBEVENT_SERVICE_LEVEL_CONNECTION_ESTABLISHED: {
            uint8_t status=hfp_subevent_service_level_connection_established_get_status(event);
            btstack_run_loop_remove_timer(&deadline);
            printf("SLC_COMPLETE status=%02x\n",status);
            if (!status) { acl=hfp_subevent_service_level_connection_established_get_acl_handle(event); phase="slc-ready"; }
            else phase="slc-failed";
            break;
        }
        case HFP_SUBEVENT_AUDIO_CONNECTION_ESTABLISHED: {
            uint8_t status=hfp_subevent_audio_connection_established_get_status(event);
            btstack_run_loop_remove_timer(&deadline);
            printf("SCO_COMPLETE status=%02x\n",status);
            if (!status) {
                sco=hfp_subevent_audio_connection_established_get_sco_handle(event);
                phase="sco-connected"; sco_packets=0;
                printf("RESULT SCO_LINK_ESTABLISHED handle=%04x; not end-to-end audio verification\n",sco);
            } else phase="sco-failed";
            break;
        }
        case HFP_SUBEVENT_AUDIO_CONNECTION_RELEASED:
            sco=HCI_CON_HANDLE_INVALID; phase="slc-ready"; break;
        default: break;
        }
        break;
    default: break;
    }
}
int main(void) {
    stdio_init_all();
    sleep_ms(3000);
    printf("USBPods SCO PROBE BOOT\n");
    int status=cyw43_arch_init();
    if (status) { printf("RESULT RADIO_INIT_FAILED code=%d\n",status); while(1) tight_loop_contents(); }
    l2cap_init(); rfcomm_init(); sm_init(); sdp_init();
    hci_set_master_slave_policy(0);
    gap_set_local_name("USBPods SCO Probe");
    gap_ssp_set_io_capability(SSP_IO_CAPABILITY_NO_INPUT_NO_OUTPUT);
    gap_discoverable_control(1);
    hfp_ag_init(1);
    hfp_ag_init_supported_features(0);
    hfp_ag_init_codecs(sizeof(codecs),codecs);
    hfp_ag_init_ag_indicators(sizeof(indicators)/sizeof(indicators[0]),indicators);
    hfp_ag_create_sdp_record_with_codecs(record,0x10001,1,"USBPods SCO Probe",0,0,sizeof(codecs),codecs);
    sdp_register_service(record);
    registration.callback=packet;
    hci_add_event_handler(&registration);
    hci_register_sco_packet_handler(packet);
    hfp_ag_register_packet_handler(packet);
    btstack_stdin_setup(input);
    arm("hci-startup",10000);
    status=hci_power_control(HCI_POWER_ON);
    if (status) {
        btstack_run_loop_remove_timer(&deadline);
        printf("RESULT HCI_INIT_FAILED code=%d\n",status);
        while(1) tight_loop_contents();
    }
    btstack_run_loop_execute();
    return 0;
}
