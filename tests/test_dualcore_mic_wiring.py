"""Static guards complement (never replace) target builds and live testing."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
main = (root / "src/main.c").read_text()
cmake = (root / "CMakeLists.txt").read_text()
workflow = (root / ".github/workflows/pico-firmware.yml").read_text()
audio = (root / "src/btstack/aacp_mic_audio.c").read_text()

assert "if(NOT USBPODS_DUAL_CORE_MIC)" in cmake
assert "target_compile_definitions(${PROJECT_NAME} PRIVATE PICO_FLASH_ASSUME_CORE1_SAFE=1)" in cmake
assert cmake.count("PICO_FLASH_ASSUME_CORE1_SAFE=1") == 1
assert "option(USBPODS_DUAL_CORE_MIC" in cmake
assert "USBPODS_DUAL_CORE_MIC requires USBPODS_MIC_DECODE=ON" in cmake
assert "_EXPERIMENTAL_Core1Mic" in cmake
assert "multicore_launch_core1_with_stack(mic_core1_entry" in main
assert main.index("multicore_launch_core1_with_stack(mic_core1_entry") < main.index("settings_init();")
assert "atomic_load_explicit(&mic_core1_decode_enabled, memory_order_acquire)" in main
assert "atomic_store_explicit(&mic_core1_decode_enabled, true, memory_order_release)" in main
assert "boot_flash_do_cmd(tx, rx, 4)" in main
assert "flash_safe_execute(boot_flash_cmd_callback, &cmd, 500)" in main
assert "boot_flash_do_cmd(sr1_tx, sr1_rx, 2)" in main
assert main.count("flash_safe_execute_core_init()") == 2
assert "atomic_store_explicit(&mic_core1_ready, true, memory_order_release)" in main
assert "atomic_load_explicit(&mic_core1_ready, memory_order_acquire)" in main
assert "#ifndef USBPODS_DUAL_CORE_MIC\n        bootsel_main_work(radio_absent);" in main
assert "mic_core1_stack[4096]" in main
assert "#ifndef USBPODS_DUAL_CORE_MIC\n            aacp_mic_audio_work();" in main
assert "aap_get" not in main.split("static void mic_core1_entry(void)")[1].split("#endif")[0]
assert "aacp_mic_audio_work();" in main.split("static void mic_core1_entry(void)")[1].split("#endif")[0]
assert "static _Atomic uint32_t aw, ar, pw, pr;" in audio
assert "memory_order_release" in audio and "memory_order_acquire" in audio
assert "matrix.dualcore || 'OFF'" in workflow
assert "matrix.dualcore != 'ON'" in workflow
assert "aaceld-core1-experimental" in workflow
print("dualcore microphone wiring guards passed")
