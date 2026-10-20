"""Profile-scoped motion policy and generated start-page behavior."""
from unittest import mock

from litebrowser.core import prefs


def test_motion_override_wins_and_system_mode_follows_platform_setting(tmp_path):
    profile = str(tmp_path)
    prefs.save_pref(profile, "reduced_motion", "reduce")
    with mock.patch.object(prefs, "_system_reduced_motion", return_value=False):
        assert prefs.reduced_motion_enabled(profile)
        assert prefs.motion_duration_ms(profile, "workspace") == 0

    prefs.save_pref(profile, "reduced_motion", "allow")
    with mock.patch.object(prefs, "_system_reduced_motion", return_value=True):
        assert not prefs.reduced_motion_enabled(profile)
        assert prefs.motion_duration_ms(profile, "workspace") == 240

    prefs.save_pref(profile, "reduced_motion", "system")
    with mock.patch.object(prefs, "_system_reduced_motion", return_value=True):
        assert prefs.reduced_motion_enabled(profile)
    with mock.patch.object(prefs, "_system_reduced_motion", return_value=False):
        assert not prefs.reduced_motion_enabled(profile)


def test_reduced_motion_suppresses_start_page_animation_only_for_that_profile(tmp_path):
    from litebrowser.browser.new_tab_page import build_new_tab_html

    reduced = str(tmp_path / "reduced")
    regular = str(tmp_path / "regular")
    prefs.save_pref(reduced, "reduced_motion", "reduce")
    prefs.save_pref(regular, "reduced_motion", "allow")

    reduced_html = build_new_tab_html(reduced)
    regular_html = build_new_tab_html(regular)

    assert "animation: none !important" in reduced_html
    assert 'class="steam"' not in reduced_html
    assert "animation: none !important" not in regular_html
    assert 'class="steam"' in regular_html
