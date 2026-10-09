"""Audio manager. Loads files from assets/sounds if present, otherwise synthesises
simple sounds with NumPy - so the game always has audio and never crashes on missing files."""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pygame

from . import settings as S

SR = 44100
SOUND_DIR = S.ASSETS_DIR / "sounds"
EXTS = (".wav", ".ogg", ".mp3")


def _sound(mono: np.ndarray, volume: float = 1.0) -> pygame.mixer.Sound:
    mono = np.clip(mono * volume, -1.0, 1.0)
    stereo = np.ascontiguousarray(np.column_stack([mono, mono]) * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(stereo)


def _t(duration: float) -> np.ndarray:
    return np.linspace(0, duration, int(SR * duration), endpoint=False)


def _tone(freq, duration, decay=8.0, harmonics=(1.0, 0.3, 0.1)) -> np.ndarray:
    t = _t(duration)
    wave = sum(a * np.sin(2 * np.pi * freq * (i + 1) * t) for i, a in enumerate(harmonics))
    attack = np.minimum(1.0, t / 0.004)
    return wave * np.exp(-decay * t) * attack / sum(harmonics)


def synth_slice() -> np.ndarray:
    rng = np.random.default_rng(1)
    t = _t(0.22)
    noise = np.diff(rng.normal(size=len(t) + 1))            # crude high-pass = "swish"
    sweep = np.sin(2 * np.pi * np.cumsum(2200 - 1600 * t / 0.22) / SR)
    return (noise * 0.5 + sweep * 0.35) * np.exp(-t * 16) * np.minimum(1, t / 0.01)


def synth_combo(step: int) -> np.ndarray:
    ratio = 2 ** (step * 2 / 12)
    return np.concatenate([_tone(f * ratio, 0.09, 10) for f in (523.25, 659.25, 783.99)])


def synth_bomb() -> np.ndarray:
    rng = np.random.default_rng(2)
    t = _t(1.3)
    noise = np.convolve(rng.normal(size=len(t)), np.ones(40) / 40, mode="same")
    thump = np.sin(2 * np.pi * np.cumsum(90 * np.exp(-t * 3)) / SR)
    return np.tanh((noise * 2.2 + thump * 1.2) * np.exp(-t * 3.2))


def synth_click() -> np.ndarray:
    return _tone(880, 0.06, 40, (1.0, 0.2))


def synth_miss() -> np.ndarray:
    t = _t(0.3)
    return np.sin(2 * np.pi * np.cumsum(170 - 90 * t / 0.3) / SR) * np.exp(-t * 10)


def synth_gameover() -> np.ndarray:
    return np.concatenate([_tone(f, 0.22, 5, (1.0, 0.5, 0.25)) for f in (392, 330, 262, 196)])


def synth_music() -> np.ndarray:
    """8-second looping arpeggio (Am F C G) with a soft bass."""
    bpm_step = 0.25
    chords = [(220.0, [220.0, 261.63, 329.63]), (174.61, [174.61, 220.0, 261.63]),
              (261.63, [261.63, 329.63, 392.0]), (196.0, [196.0, 246.94, 293.66])]
    out = np.zeros(int(SR * 8.0))
    pos = 0
    for bass, notes in chords:
        for i in range(8):
            f = notes[[0, 1, 2, 1, 0, 1, 2, 1][i]] * 2
            n = _tone(f, 0.45, 6, (1.0, 0.25))
            out[pos:pos + len(n)] += n[:len(out) - pos] * 0.5
            if i % 4 == 0:
                b = _tone(bass / 2, 0.9, 2.5, (1.0, 0.2))
                out[pos:pos + len(b)] += b[:len(out) - pos] * 0.7
            pos += int(SR * bpm_step)
    return out / max(1.0, np.abs(out).max()) * 0.9


class AudioManager:
    def __init__(self, settings: S.UserSettings) -> None:
        self.settings = settings
        self.available = False
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self.combo_sounds: List[pygame.mixer.Sound] = []
        self.music_sound: Optional[pygame.mixer.Sound] = None
        self.music_channel: Optional[pygame.mixer.Channel] = None
        self.music_file: Optional[str] = None
        self._music_playing = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(SR, -16, 2, 512)
            pygame.mixer.set_num_channels(16)
            self.available = True
        except Exception as exc:
            print(f"[audio] disabled: {exc}")
            return
        self._load()

    # ------------------------------------------------------------------ loading
    def _find(self, name: str) -> Optional[str]:
        for ext in EXTS:
            p = SOUND_DIR / f"{name}{ext}"
            if p.exists():
                return str(p)
        return None

    def _load_one(self, name: str, fallback, volume: float) -> pygame.mixer.Sound:
        path = self._find(name)
        if path:
            try:
                snd = pygame.mixer.Sound(path)
                snd.set_volume(volume)
                return snd
            except Exception as exc:
                print(f"[audio] could not load {path}: {exc}")
        return _sound(fallback(), volume)

    def _load(self) -> None:
        try:
            self.sounds["slice"] = self._load_one("slice", synth_slice, 0.55)
            self.sounds["bomb"] = self._load_one("bomb", synth_bomb, 0.8)
            self.sounds["click"] = self._load_one("click", synth_click, 0.5)
            self.sounds["miss"] = self._load_one("miss", synth_miss, 0.6)
            self.sounds["gameover"] = self._load_one("gameover", synth_gameover, 0.6)
            path = self._find("combo")
            if path:
                self.combo_sounds = [self._load_one("combo", lambda: np.zeros(10), 0.6)]
            else:
                self.combo_sounds = [_sound(synth_combo(i), 0.5) for i in range(5)]
            self.music_file = self._find("music")
            if not self.music_file:
                self.music_sound = _sound(synth_music(), 0.35)
                self.music_channel = pygame.mixer.Channel(0)
        except Exception as exc:
            print(f"[audio] loading failed, continuing silently: {exc}")
            self.available = False

    # ------------------------------------------------------------------ playback
    def play(self, name: str) -> None:
        if self.available and self.settings.sound_on and name in self.sounds:
            self.sounds[name].play()

    def play_combo(self, level: int) -> None:
        if self.available and self.settings.sound_on and self.combo_sounds:
            self.combo_sounds[min(max(level - 2, 0), len(self.combo_sounds) - 1)].play()

    def click(self) -> None:
        self.play("click")

    def start_music(self) -> None:
        if not (self.available and self.settings.music_on):
            return
        try:
            if self.music_file:
                pygame.mixer.music.load(self.music_file)
                pygame.mixer.music.set_volume(0.4)
                pygame.mixer.music.play(-1)
            elif self.music_sound and self.music_channel:
                self.music_channel.play(self.music_sound, loops=-1)
            self._music_playing = True
        except Exception as exc:
            print(f"[audio] music failed: {exc}")

    def stop_music(self) -> None:
        if not self.available:
            return
        try:
            pygame.mixer.music.stop()
            if self.music_channel:
                self.music_channel.stop()
        except Exception:
            pass
        self._music_playing = False

    def pause_music(self) -> None:
        if self.available and self._music_playing:
            pygame.mixer.music.pause()
            if self.music_channel:
                self.music_channel.pause()

    def resume_music(self) -> None:
        if not self.available:
            return
        if not self.settings.music_on:
            return
        if self._music_playing:
            pygame.mixer.music.unpause()
            if self.music_channel:
                self.music_channel.unpause()
        else:
            self.start_music()

    def apply_settings(self) -> None:
        """Call after toggling Sound/Music in the settings menu."""
        if not self.settings.music_on:
            self.stop_music()
