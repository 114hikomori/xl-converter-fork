from unittest.mock import patch

import pytest

from data.sounds import SoundPlayer


@pytest.fixture
def player():
    return SoundPlayer("/fake/path/sound.wav", volume=0.7)

def test_init_stores_config(player):
    assert player.sound is None
    assert player.volume == 0.7
    assert player.audio_path == "/fake/path/sound.wav"

def test_play_first_call_no_argument_uses_configured_default(app, player):
    """Regression test: play() with no volume argument must apply the
    instance's configured self.volume to the freshly-created QSoundEffect,
    not the raw (None) method parameter - PySide6's typed binding raises
    TypeError on QSoundEffect.setVolume(None)."""
    player.play()
    assert player.sound.volume() == pytest.approx(0.7)

def test_play_first_call_explicit_argument_overrides_default(app, player):
    player.play(volume=0.2)
    assert player.sound.volume() == pytest.approx(0.2)

def test_play_reuses_existing_sound_object(app, player):
    player.play()
    first_sound = player.sound
    player.play()
    assert player.sound is first_sound

def test_play_later_call_explicit_volume_overrides_after_creation(app, player):
    player.play()               # Creates with default 0.7
    player.play(volume=0.3)     # Overrides on the existing object
    assert player.sound.volume() == pytest.approx(0.3)

def test_play_sets_source_from_audio_path(app, player):
    player.play()
    assert player.audio_path in player.sound.source().toLocalFile()

def test_play_calls_underlying_play(app, player):
    player.play()  # First call creates the real QSoundEffect
    with patch.object(player.sound, "play") as mock_play:
        player.play()
    mock_play.assert_called_once()
