"""Production duplex profile matcher: explicit negative controls for stale game state.

No device/COM/host audio is accessed. This test uses the real live_audio
profile matching and health functions; it cannot establish Pico schedulability.
"""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import live_audio


def state(profile, ceiling=256000, mic_build=True):
    _, rate, game, level, bitrate, vbr, sbr, slots = profile
    if mic_build:
        vbr = sbr = 0
    jitter = 60 if game and level == 2 else 90 if game else 150
    return dict(
        ready=1, pending=0, transition="ready", input_rate=48000,
        requested_revision=7, built_revision=7, selected_rate=rate,
        game=int(game), gamelevel=level, desired_bitrate=bitrate,
        active_bitrate=bitrate, active_vbr=vbr, active_sbr=sbr,
        active_slots=slots, active_jitter=jitter, desired_jitter=jitter,
        duplex_cbr=int(mic_build), negotiated_bitrate=ceiling,
        negotiated_vbr=1,
    )


def pre_patch_match(s, profile):
    """The exact old field set, proving the relevant false-green negative."""
    _, _, _, _, bitrate, vbr, sbr, slots = profile
    if s.get("negotiated_vbr") == 0 or s.get("duplex_cbr") == 1:
        vbr = sbr = 0
    return (
        s.get("ready") == 1 and not s.get("pending")
        and s.get("transition") == "ready" and s.get("input_rate") == 48000
        and s.get("requested_revision") == s.get("built_revision")
        and all(s.get(k) == v for k, v in (
            ("active_bitrate", bitrate), ("active_vbr", vbr),
            ("active_sbr", sbr), ("active_slots", slots),
        ))
    )


class AppliedPolicy(unittest.TestCase):
    def test_valid_profiles_and_ceiling(self):
        for profile in live_audio.PROFILES:
            ceiling = 320000 if profile[0] == "eld320" else 256000
            for mic_build in (False, True):
                with self.subTest(profile=profile[0], mic_build=mic_build):
                    s = state(profile, ceiling=ceiling, mic_build=mic_build)
                    self.assertTrue(live_audio.profile_matches(s, profile))
        self.assertFalse(live_audio.profile_matches(
            state(live_audio.PROFILES[2], ceiling=256000), live_audio.PROFILES[2]))
        # Games request selector 3 but build a 192 kbps codec under a 256k peer.
        self.assertTrue(live_audio.profile_matches(
            state(live_audio.PROFILES[3], ceiling=256000), live_audio.PROFILES[3]))
        self.assertTrue(live_audio.profile_matches(
            state(live_audio.PROFILES[4], ceiling=256000), live_audio.PROFILES[4]))

    def test_normal_192_is_not_game_standard(self):
        normal = state(live_audio.PROFILES[1])
        game = live_audio.PROFILES[3]
        self.assertTrue(pre_patch_match(normal, game))  # old code false PASS
        self.assertFalse(live_audio.profile_matches(normal, game))

    def test_selected_game_with_stale_active_192_is_rejected(self):
        game = live_audio.PROFILES[3]
        stale = state(game)
        stale["active_jitter"] = 150  # pre-game normal-192 encoder policy
        self.assertTrue(pre_patch_match(stale, game))
        self.assertFalse(live_audio.profile_matches(stale, game))

    def test_stale_or_missing_fields_fail_closed(self):
        profile = live_audio.PROFILES[3]
        for key, bad in (
            ("selected_rate", 1), ("game", 0), ("gamelevel", 2),
            ("desired_bitrate", 256000), ("active_bitrate", 256000),
            ("active_slots", 4), ("active_jitter", 150),
            ("desired_jitter", 150), ("requested_revision", 8),
            ("negotiated_bitrate", 128000), ("pending", 1),
        ):
            with self.subTest(key=key):
                item = state(profile)
                item[key] = bad
                self.assertFalse(live_audio.profile_matches(item, profile))
                del item[key]
                self.assertFalse(live_audio.profile_matches(item, profile))

    def test_relay_uses_existing_preference_with_164k_cap(self):
        for baseline in (live_audio.PROFILES[-1], live_audio.PROFILES[1]):
            relay = ("relay", *baseline[1:4], 164000, 0, 0, 6)
            self.assertTrue(live_audio.profile_matches(state(relay), relay))

    def test_strict_loss_accounting_unchanged(self):
        def sample(decoded, samples, au_drop=0, missing=0):
            return {
                "status": {"streaming": 1, "codec": 4, "tx_packets": 100 + decoded, "send_failures": 0},
                "eldstatus": {"transition": "ready"},
                "micstats": {"generation": 3, "capture": 1, "decoded": decoded,
                             "clock_windows": 1, "measured_rate": 64000,
                             "coding_rate": 48000, "pcm_rate": 64000,
                             "errors": 0, "au_drop": au_drop, "pcm_drop": 0},
                "usbcapture": {"running": 1, "pcm_samples": samples,
                               "missing_samples": missing, "short_writes": 0},
            }
        before = sample(1, 100)
        self.assertEqual(live_audio.health(before, sample(2, 164)), [])
        self.assertTrue(any("au_drop" in e for e in
            live_audio.health(before, sample(2, 164, au_drop=1))))
        self.assertTrue(any("missing_samples" in e for e in
            live_audio.health(before, sample(2, 164, missing=1))))

    def test_steady_interval_rejects_unexpected_profile_change(self):
        profile = live_audio.PROFILES[3]
        def sample(decoded, jitter=90):
            applied = state(profile)
            applied["active_jitter"] = jitter
            return dict(
                status=dict(streaming=1, codec=4, tx_packets=decoded, send_failures=0),
                eldstatus=applied,
                micstats=dict(generation=1,capture=1,decoded=decoded,
                              clock_windows=1,measured_rate=64000,
                              coding_rate=48000,pcm_rate=64000,
                              errors=0,au_drop=0,pcm_drop=0),
                usbcapture=dict(running=1,pcm_samples=decoded*480,
                                missing_samples=0,short_writes=0),
            )
        before=sample(10)
        self.assertEqual(live_audio.health(before,sample(11),profile),[])
        # A mid-interval policy change cannot be called a passing game test
        # even though zero AU, decoder, and USB errors were observed.
        self.assertIn("Applied ELD profile mismatch at end of steady interval",
                      live_audio.health(before,sample(11,jitter=150),profile))

    def test_firmware_status_exposes_applied_policy_not_only_preference(self):
        c_source = (ROOT / "src/device_control.c").read_text()
        self.assertIn(r'active_jitter\":%u', c_source)
        self.assertIn(r'desired_jitter\":%u', c_source)
        self.assertIn("state.active.slots,state.active.jitter,state.desired.jitter,state.active.input_rate", c_source)

    def test_sampled_profile_drift_and_mic_recovery_remain_failures(self):
        profile=live_audio.PROFILES[3]
        good=dict(status=dict(streaming=1,codec=4,mic_started=1,mic_recovery_pending=0),
                  eldstatus=state(profile))
        self.assertEqual(live_audio.steady_state_errors(good,profile),[])
        drift=copy.deepcopy(good)
        drift['eldstatus']['active_jitter']=150
        faults=live_audio.steady_state_errors(drift,profile)
        self.assertTrue(any('requested ready profile' in error for error in faults))
        self.assertEqual(live_audio.steady_state_errors(good,profile),[])
        # Recovery at the endpoint cannot erase an earlier sampled failure.
        self.assertTrue(faults)
        recovery=copy.deepcopy(good)
        recovery['status']['mic_recovery_pending']=1
        self.assertTrue(any('Microphone' in error for error in
                            live_audio.steady_state_errors(recovery,profile)))


if __name__ == "__main__":
    unittest.main()
