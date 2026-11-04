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
