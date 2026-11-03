cmake_minimum_required(VERSION 3.13)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(usbpods_sco_probe C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()
add_executable(usbpods_sco_probe main.c)
# The probe uses the SDK's CDC-only USB console, not USBPods' audio config.
# Select it explicitly: GCC searches normal includes before SDK system
# includes even when CMake lists the SDK directory first.
target_include_directories(usbpods_sco_probe PRIVATE ${CMAKE_CURRENT_LIST_DIR}/../..)
target_compile_definitions(usbpods_sco_probe PRIVATE
    CFG_TUSB_CONFIG_FILE=\"${PICO_SDK_PATH}/src/rp2_common/pico_stdio_usb/include/tusb_config.h\")
target_link_libraries(usbpods_sco_probe PRIVATE pico_stdlib pico_cyw43_arch_none
    pico_btstack_cyw43 pico_btstack_ble pico_btstack_classic)
pico_enable_stdio_usb(usbpods_sco_probe 1)
pico_enable_stdio_uart(usbpods_sco_probe 0)
pico_add_extra_outputs(usbpods_sco_probe)
