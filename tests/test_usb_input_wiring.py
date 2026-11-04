"""Verify that TinyUSB callbacks actually use the production-tested helpers."""
import re
from pathlib import Path
source = Path("src/tinyusb/uac.c").read_text()
cmake = Path("CMakeLists.txt").read_text()
def section(start, end):
    assert start in source and end in source
    return source.split(start, 1)[1].split(end, 1)[0]
assert "usb_capture_mount();" in section("void tud_mount_cb", "void tud_umount_cb")
assert "usb_capture_unmount();" in section("void tud_umount_cb", "void tud_suspend_cb")
assert "usb_capture_suspend();" in section("void tud_suspend_cb", "void tud_resume_cb")
assert "usb_capture_resume();" in section("void tud_resume_cb", "static bool tud_audio_clock_get_request")
assert "usb_capture_close();" in section("bool tud_audio_set_itf_close_EP_cb", "bool tud_audio_set_itf_cb")
assert "usb_capture_set_alt(alt == 1);" in section("bool tud_audio_set_itf_cb", "uint16_t usb_stop_delay")
tx = section("bool tud_audio_tx_done_pre_load_cb", "// AUDIO Task")
assert "itf != 0" in tx  # TinyUSB 0.18 func_id, NOT USB interface number
assert "usb_capture_running()" in tx and "usb_capture_note_tx(want,got,written);" in tx
assert "usb_hid_media_poll(ready, usb_hid_send_report);" in source
assert "usb_hid_media_enqueue(usage);" in source
for entry in ("src/tinyusb/usb_capture_lifecycle.c", "src/tinyusb/usb_hid_media.c"):
    assert entry in cmake

# 'u'/'k' change a boot-latched setting: a USB replug does NOT re-run main(),
# so the console must say reboot (device_control.c's reboot_required wording).
console = Path("src/console.c").read_text()
for key in ("u", "k"):
    start = f"case '{key}':"
    assert start in console
    block = console.split(start, 1)[1].split("break;", 1)[0]
    assert "reboot to apply" in block, (key, block)
    assert "replug USB to apply" not in block, (key, block)

# usb_desc_set_uac1_first() is latched once in main() before tinyusb_main();
# it must not be re-latched from a mount/umount/suspend/resume/mode callback.
main = Path("src/main.c").read_text()
call = "usb_desc_set_uac1_first((read_settings_byte() & USBSET_UAC1) != 0);"
assert call in main
assert main.index(call) < main.index("tinyusb_main();")
for start, end in (("void tud_mount_cb", "void tud_umount_cb"),
                   ("void tud_umount_cb", "void tud_suspend_cb"),
                   ("void tud_suspend_cb", "void tud_resume_cb"),
                   ("void tud_resume_cb", "static bool tud_audio_clock_get_request")):
    assert "usb_desc_set_uac1_first" not in section(start, end)
mode_block = source.split("static void usb_mode_task", 1)[1].split("\n }", 1)[0]
assert "usb_desc_set_uac1_first" not in mode_block
call_sites = []
for path in Path("src").rglob("*.[ch]"):
    text = path.read_text(errors="ignore")
    call_sites.extend((str(path), match.start())
                      for match in re.finditer(r'(?<!void )\busb_desc_set_uac1_first\s*\(', text))
assert [path for path, _ in call_sites] == ["src/main.c"], call_sites
print("TinyUSB production callback wiring verified")

# Main-loop code must not mutate BTstack/AVRCP state without the cyw43
# async-context lock (the BT run loop preempts thread mode). The connmode-3
# dial and the host-volume apply are the two main-loop BT mutators.
assert "bt_async_lock_take()" in source and "bt_async_lock_give()" in source
assert "async_context_acquire_lock_blocking(ctx);" in source
vol_block = source.split("static bool apply_host_fu_volume", 1)[1].split("\n}", 1)[0]
assert "bt_async_lock_take()" in vol_block, vol_block
assert "set_bt_volume(" in vol_block
assert "bt_async_lock_give();" in vol_block
mode_block2 = source.split("static void usb_mode_task", 1)[1].split("\n }", 1)[0]
assert "a2dp_source_reconnect();" in mode_block2
assert "bt_async_lock_take()" in mode_block2 and "bt_async_lock_give();" in mode_block2

# No radio: the console and the USB mode task must not touch BT/SDK state.
assert "radio_is_absent()" in source
assert "Bluetooth unavailable (no radio)" in console
console_key_block = console.split("void console_key(char cmd){", 1)[1].split("switch (cmd){", 1)[0]
assert "radio_is_absent()" in console_key_block
assert console_key_block.index("radio_is_absent()") < console_key_block.index("a2dp_source_console_key")
print("TinyUSB production callback wiring verified")

# Main-loop TinyUSB writes are serialized against the timer-IRQ tud_task with
# a short interrupt-disabled section (single core: no other writer can enter).
assert "usb_tx_irq_save()" in source and "save_and_disable_interrupts()" in source
assert "restore_interrupts(" in source
hid_block = source.split("static bool usb_hid_send_report", 1)[1].split("}", 1)[0]
assert "usb_tx_irq_save()" in hid_block and "usb_tx_irq_restore(" in hid_block
assert "tud_hid_report(1, &usage, sizeof(usage))" in hid_block
int_writes = [i for i in range(len(source)) if source.startswith("tud_audio_int_write", i)]
assert len(int_writes) == 2  # both call sites must be IRQ-serialized
for pos in int_writes:
    saved = source.rfind("usb_tx_irq_save()", 0, pos)
    assert saved != -1 and pos - saved < 220, "main-loop tud_audio_int_write is not IRQ-serialized"
    closed = source.find("usb_tx_irq_restore(", pos)
    assert closed != -1 and closed - pos < 160

# UAC1 endpoint max packet must follow the advertised rate (44.1 -> 180).
uac1 = Path("src/tinyusb/uac1_descriptors.h").read_text()
assert "#define UAC1_EP_OUT_SZ_44   180" in uac1
assert "U16_TO_U8S_LE(_epsz)" in uac1
usbd = Path("src/tinyusb/usb_descriptors.c").read_text()
assert "UAC1_RATE_48_3B, UAC1_EP_OUT_SZ_48" in usbd
assert "UAC1_RATE_44_3B, UAC1_EP_OUT_SZ_44" in usbd
print("TinyUSB production callback wiring verified")

# UAC1 must arm one packet at the active personality's advertised max size
# (192 B at 48 kHz, 180 B at 44.1 kHz), not always the 192-byte buffer size.
u1 = Path("src/tinyusb/uac1_device.c").read_text()
arm = u1.split("static void spk_arm(void)", 1)[1].split("\n}", 1)[0]
assert "tu_edpt_packet_size(&s_ep_out_desc)" in arm
assert "UAC1_EP_OUT_SZ" not in arm
xfer = u1.split("static bool uac1_xfer_cb", 1)[1]
assert xfer.find("XFER_RESULT_SUCCESS") < xfer.find("audio_slot_push_samples"), \
    "failed ISO transfer must not publish its stale buffer"
guard = xfer.split("XFER_RESULT_SUCCESS", 1)[1]
assert "spk_arm();" in guard.split("audio_slot_push_samples", 1)[0]

# CDC input is the documented diagnostic transport: service it before UART so
# a noisy UART RX cannot starve console commands.
serial = Path("src/tinyusb/usb_serial.c").read_text()
block = serial.split("static int cdc_in_chars", 1)[1].split("PICO_ERROR_NO_DATA;\n}", 1)[0]
assert block.find("tud_cdc_read") < block.find("USBSET_UART")
print("TinyUSB production callback wiring verified")
