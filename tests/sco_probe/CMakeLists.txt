cmake_minimum_required(VERSION 3.13)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(usbpods_sco_probe C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()
add_executable(usbpods_sco_probe main.c)
# The probe uses the SDK's CDC-only USB console, not USBPods' audio config.
# Keep this ahead of the repository root, which contains the application's
# tusb_config.h as well as the shared btstack_config.h we need.
target_include_directories(usbpods_sco_probe BEFORE PRIVATE
    ${PICO_SDK_PATH}/src/rp2_common/pico_stdio_usb/include
    ${CMAKE_CURRENT_LIST_DIR}/../..)
target_link_libraries(usbpods_sco_probe PRIVATE pico_stdlib pico_cyw43_arch_none
    pico_btstack_cyw43 pico_btstack_ble pico_btstack_classic)
pico_enable_stdio_usb(usbpods_sco_probe 1)
pico_enable_stdio_uart(usbpods_sco_probe 0)
pico_add_extra_outputs(usbpods_sco_probe)
