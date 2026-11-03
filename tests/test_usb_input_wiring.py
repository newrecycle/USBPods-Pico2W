"""Verify that TinyUSB callbacks actually use the production-tested helpers."""
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
assert "usb_capture_running()" in tx and "usb_capture_note_tx(got, written);" in tx
assert "usb_hid_media_poll(ready, usb_hid_send_report);" in source
assert "usb_hid_media_enqueue(usage);" in source
for entry in ("src/tinyusb/usb_capture_lifecycle.c", "src/tinyusb/usb_hid_media.c"):
    assert entry in cmake
print("TinyUSB production callback wiring verified")
