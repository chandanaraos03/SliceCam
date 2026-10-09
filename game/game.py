"""Main Game class: state machine, update loop and rendering."""
from __future__ import annotations

import math
import random
import textwrap
from enum import Enum, auto
from typing import List, Optional

import cv2
import pygame

from vision import HAND_CONNECTIONS, VisionSystem

from . import settings as S
from .audio import AudioManager
from .bomb import Bomb
from .collision import segment_hits_circle
from .fruit import Fruit, FruitHalf, FlyingObject
from .input_source import CameraInput, MouseInput
from .particles import ParticleSystem, get_glow
from .player import Blade, PlayerState
from .ui import Button, Fonts, draw_heart, draw_text, make_background, make_vignette, panel

W, H = S.SCREEN_W, S.SCREEN_H


class State(Enum):
    MENU = auto()
    SETTINGS = auto()
    CALIBRATION = auto()
    PLAYING = auto()
    PAUSED = auto()
    GAME_OVER = auto()


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption(S.TITLE)
        self.screen = self._create_window()
        self.canvas = pygame.Surface((W, H)).convert()   # everything is drawn at 1280x720
        self.clock = pygame.time.Clock()
        self.settings = S.UserSettings.load()
        self.audio = AudioManager(self.settings)
        self.fonts = Fonts()
        self.background = make_background(W, H).convert()
        self.vignette = make_vignette(W, H).convert_alpha()
        self.running = True
        self.debug = False

        self.state = State.MENU
        self.mode = "mouse"                      # "mouse" | "camera"
        self.vision: Optional[VisionSystem] = None
        self.input = MouseInput(self._mouse_pos)
        self.blade = Blade(self.settings.blade_trail)
        self.player = PlayerState(self.settings.best_score)
        self.particles = ParticleSystem()
        self.objects: List[FlyingObject] = []
        self.halves: List[FruitHalf] = []
        self.spawn_queue: list = []
        self.menu_fruits: List[Fruit] = []
        self.menu_timer = 0.0
        self.time = 0.0
        self.spawn_timer = 1.0
        self.waves = 0
        self.ending = False
        self.ending_timer = 0.0
        self.ending_reason = ""
        self.shake = 0.0
        self.flash = 0.0
        self.miss_flash = 0.0
        self.life_pulse = 0.0
        self.new_best = False
        self.toast = ("", 0.0)
        self._cam_cache = (None, None)           # ((frame_id, mode), surface)
        self._view = (0, 0, 1.0)                 # letterbox offset/scale when SCALED is unavailable
        self.calib_msg_timer = 0.0
        self.buttons: dict = {}
        self._build_buttons()

    # ================================================================== setup
    def _create_window(self) -> pygame.Surface:
        for flags, kwargs in ((pygame.SCALED | pygame.RESIZABLE, {"vsync": 1}),
                              (pygame.SCALED | pygame.RESIZABLE, {}),
                              (pygame.RESIZABLE, {})):
            try:
                return pygame.display.set_mode((W, H), flags, **kwargs)
            except Exception:
                continue
        return pygame.display.set_mode((W, H))

    def _mouse_pos(self):
        return self._map_pos(pygame.mouse.get_pos())

    def _map_pos(self, pos):
        """Window coordinates -> logical 1280x720 coordinates (only differs without SCALED)."""
        ox, oy, scale = self._view
        return ((pos[0] - ox) / scale, (pos[1] - oy) / scale)

    def _build_buttons(self) -> None:
        cx = W // 2
        b = Button
        self.buttons = {
            State.MENU: [b("CAMERA MODE", (cx, 320), accent=S.CYAN), b("MOUSE MODE", (cx, 400), accent=S.LIME),
                         b("SETTINGS", (cx, 480), accent=S.MAGENTA), b("QUIT", (cx, 560), accent=S.GREY)],
            State.PAUSED: [b("RESUME", (cx, 330), accent=S.LIME), b("RESTART", (cx, 410), accent=S.CYAN),
                           b("MAIN MENU", (cx, 490), accent=S.MAGENTA)],
            State.GAME_OVER: [b("PLAY AGAIN", (cx, 480), accent=S.LIME), b("MAIN MENU", (cx, 560), accent=S.MAGENTA)],
            State.CALIBRATION: [b("BACK", (130, H - 50), (200, 56), S.GREY, 24),
                                b("", (W - 190, H - 50), (320, 56), S.MAGENTA, 22)],
            State.SETTINGS: [],
        }
        rows = ["sound", "music", "camera", "trail", "difficulty", "mirror"]
        self.settings_rows = rows
        self.buttons[State.SETTINGS] = [b("", (cx, 190 + i * 68), (520, 56), S.CYAN, 24) for i in range(len(rows))]
        self.buttons[State.SETTINGS].append(b("BACK", (cx, 190 + len(rows) * 68 + 20), (260, 56), S.GREY, 24))
        self.camera_error_buttons = [b("TRY AGAIN", (cx - 170, 630), (300, 58), S.LIME, 24),
                                     b("BACK", (cx + 170, 630), (300, 58), S.GREY, 24)]
        self._refresh_setting_labels()

    def _refresh_setting_labels(self) -> None:
        st = self.settings
        labels = [f"Sound:  {'ON' if st.sound_on else 'OFF'}",
                  f"Music:  {'ON' if st.music_on else 'OFF'}",
                  f"Camera Background:  {st.camera_background}",
                  f"Blade Trail:  {st.blade_trail}",
                  f"Difficulty:  {st.difficulty}",
                  f"Mirror Camera:  {'ON' if st.mirror_camera else 'OFF'}"]
        for btn, text in zip(self.buttons[State.SETTINGS], labels):
            btn.label = text
        cal = self.buttons[State.CALIBRATION][1]
        cal.label = f"Mirror: {'ON' if st.mirror_camera else 'OFF'}  (M)"

    # ================================================================== flow
    def run(self) -> None:
        try:
            while self.running:
                dt = min(self.clock.tick(S.FPS) / 1000.0, 0.05)
                self.handle_events()
                self.update(dt)
                self.draw()
                self.present()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self._stop_vision()
        self.settings.best_score = max(self.settings.best_score, self.player.best_score)
        self.settings.save()
        self.audio.stop_music()
        pygame.quit()

    def _stop_vision(self) -> None:
        if self.vision is not None:
            self.vision.stop()
            self.vision = None

    def go_menu(self) -> None:
        self.audio.stop_music()
        self._stop_vision()
        pygame.mouse.set_visible(True)
        self.state = State.MENU

    def start_camera_mode(self) -> None:
        self.mode = "camera"
        self._start_vision()
        self.state = State.CALIBRATION

    def _start_vision(self) -> None:
        self._stop_vision()
        self.vision = VisionSystem(S.CAMERA_INDEX, self.settings.mirror_camera, S.CAMERA_REQUEST_SIZE)
        self.vision.start()
        self.input = CameraInput(self.vision)

    def start_mouse_mode(self) -> None:
        self.mode = "mouse"
        self._stop_vision()
        self.input = MouseInput(self._mouse_pos)
        self.begin_game()

    def begin_game(self) -> None:
        self.player.reset()
        self.objects.clear()
        self.halves.clear()
        self.spawn_queue.clear()
        self.particles = ParticleSystem()
        self.blade = Blade(self.settings.blade_trail)
        self.time = 0.0
        self.spawn_timer = 0.8
        self.waves = 0
        self.ending = False
        self.shake = self.flash = self.miss_flash = 0.0
        self.new_best = False
        self.input.reset()
        pygame.mouse.set_visible(False)
        self.audio.stop_music()
        self.audio.start_music()
        self.state = State.PLAYING

    def pause(self) -> None:
        self.state = State.PAUSED
        self.audio.pause_music()
        pygame.mouse.set_visible(True)

    def resume(self) -> None:
        self.state = State.PLAYING
        self.input.reset()
        self.blade.clear()
        self.audio.resume_music()
        pygame.mouse.set_visible(False)

    def finish_game(self) -> None:
        self.new_best = self.player.score > 0 and self.player.score >= self.settings.best_score
        self.settings.best_score = max(self.settings.best_score, self.player.score)
        self.player.best_score = self.settings.best_score
        self.settings.save()
        self.audio.stop_music()
        self.audio.play("gameover")
        pygame.mouse.set_visible(True)
        self.state = State.GAME_OVER

    def show_toast(self, text: str) -> None:
        self.toast = (text, 1.6)

    def toggle_mirror(self) -> None:
        self.settings.mirror_camera = not self.settings.mirror_camera
        if self.vision:
            self.vision.set_mirror(self.settings.mirror_camera)
        self.settings.save()
        self._refresh_setting_labels()
        self.show_toast(f"Camera mirror: {'ON' if self.settings.mirror_camera else 'OFF'}")

    # ================================================================== events
    def handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._on_key(event)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._on_click(self._map_pos(event.pos))

    def _on_key(self, event) -> None:
        k, st = event.key, self.state
        if k == pygame.K_F11:
            try:
                pygame.display.toggle_fullscreen()
            except Exception:
                pass
        elif k == pygame.K_F3:
            self.debug = not self.debug
        elif k == pygame.K_m and self.mode == "camera" and st in (State.CALIBRATION, State.PLAYING, State.PAUSED):
            self.toggle_mirror()
        elif k == pygame.K_ESCAPE:
            if st == State.PLAYING:
                self.pause()
            elif st == State.PAUSED:
                self.resume()
            elif st in (State.CALIBRATION, State.SETTINGS, State.GAME_OVER):
                self.audio.click()
                self.go_menu()
        elif k == pygame.K_r and st in (State.PLAYING, State.PAUSED, State.GAME_OVER):
            self.audio.click()
            self.begin_game()
        elif k == pygame.K_SPACE and st == State.CALIBRATION:
            self._try_start_from_calibration()

    def _try_start_from_calibration(self) -> None:
        if self.vision and self.vision.status == "running" and self.input.hand_detected:
            self.audio.click()
            self.begin_game()
        else:
            self.calib_msg_timer = 1.5

    def _on_click(self, pos) -> None:
        st = self.state
        if st == State.CALIBRATION and self.vision and self.vision.status == "error":
            again, back = self.camera_error_buttons
            if again.hit(pos):
                self.audio.click(); self._start_vision()
            elif back.hit(pos):
                self.audio.click(); self.go_menu()
            return
        for i, btn in enumerate(self.buttons.get(st, [])):
            if not btn.hit(pos):
                continue
            self.audio.click()
            if st == State.MENU:
                [self.start_camera_mode, self.start_mouse_mode,
                 lambda: setattr(self, "state", State.SETTINGS), lambda: setattr(self, "running", False)][i]()
            elif st == State.PAUSED:
                [self.resume, self.begin_game, self.go_menu][i]()
            elif st == State.GAME_OVER:
                [self.begin_game, self.go_menu][i]()
            elif st == State.CALIBRATION:
                if i == 0:
                    self.go_menu()
                else:
                    self.toggle_mirror()
            elif st == State.SETTINGS:
                self._on_setting(i)
            return

    def _on_setting(self, i: int) -> None:
        st = self.settings
        if i >= len(self.settings_rows):
            st.save(); self.state = State.MENU; return
        row = self.settings_rows[i]
        cycle = lambda cur, opts: opts[(opts.index(cur) + 1) % len(opts)]
        if row == "sound":
            st.sound_on = not st.sound_on
        elif row == "music":
            st.music_on = not st.music_on
            self.audio.apply_settings()
        elif row == "camera":
            st.camera_background = cycle(st.camera_background, S.CAMERA_BACKGROUNDS)
        elif row == "trail":
            st.blade_trail = cycle(st.blade_trail, list(S.TRAIL_LEVELS))
            self.blade.set_level(st.blade_trail)
        elif row == "difficulty":
            st.difficulty = cycle(st.difficulty, list(S.DIFFICULTY))
        elif row == "mirror":
            self.toggle_mirror(); return
        st.save()
        self._refresh_setting_labels()

    # ================================================================== update
    def update(self, dt: float) -> None:
        mouse = self._mouse_pos()
        for btn in self.buttons.get(self.state, []):
            btn.update(mouse, dt)
        for btn in self.camera_error_buttons:
            btn.update(mouse, dt)
        self.toast = (self.toast[0], max(0.0, self.toast[1] - dt))
        self.calib_msg_timer = max(0.0, self.calib_msg_timer - dt)

        if self.state == State.MENU or self.state == State.SETTINGS:
            self._update_menu_fruits(dt)
        elif self.state == State.CALIBRATION:
            if isinstance(self.input, CameraInput):
                self.input.update(dt)
        elif self.state == State.PLAYING:
            self._update_playing(dt)

    def _update_menu_fruits(self, dt: float) -> None:
        self.menu_timer -= dt
        if self.menu_timer <= 0:
            self.menu_timer = random.uniform(0.7, 1.4)
            self.menu_fruits.append(self._launch(random.choice(list(S.FRUITS)), S.GRAVITY * 0.8))
        for f in self.menu_fruits:
            f.update(dt)
        self.menu_fruits = [f for f in self.menu_fruits if not f.is_missed()]

    # ---------------------------------------------------------------- gameplay
    def _progress(self) -> float:
        cfg = S.DIFFICULTY[self.settings.difficulty]
        p = min(1.0, self.player.score / cfg["score_for_max"])
        return p * p * (3 - 2 * p)  # smoothstep: gentle start, no sudden jumps

    def _launch(self, kind: Optional[str], gravity: float) -> FlyingObject:
        """Create a fruit (kind) or a bomb (kind=None) flying up from below the screen."""
        radius = S.BOMB_RADIUS if kind is None else S.FRUITS[kind]["radius"]
        x = random.uniform(0.12, 0.88) * W
        target_x = random.uniform(0.2, 0.8) * W
        rise = random.uniform(0.55, 0.9) * H            # how high the apex is above the spawn point
        t_apex = math.sqrt(2 * rise / gravity)
        vy = -gravity * t_apex                          # v = g*t  ->  apex exactly `rise` px higher
        vx = (target_x - x) / t_apex                    # reaches target_x at the apex
        rot = random.choice((-1, 1)) * random.uniform(90, 330)
        y = H + radius * 1.2
        if kind is None:
            return Bomb(x, y, vx, vy, gravity, rot)
        return Fruit(kind, x, y, vx, vy, gravity, rot)

    def _spawn_wave(self) -> None:
        cfg, d = S.DIFFICULTY[self.settings.difficulty], self._progress()
        n = random.randint(1, max(1, round(lerp(*cfg["wave_max"], d))))
        bomb_p = lerp(*cfg["bomb"], d) if self.waves >= 3 else 0.0   # no bombs in the first waves
        gravity = S.GRAVITY * lerp(*cfg["gravity"], d)
        for i in range(n):
            is_bomb = random.random() < (bomb_p if i > 0 else bomb_p * 0.5)
            self.spawn_queue.append([i * 0.11 + random.uniform(0, 0.05), is_bomb, gravity])
        self.waves += 1

    def _update_playing(self, dt: float) -> None:
        self.time += dt
        inp = self.input.update(dt)
        self.blade.update(inp.visible, inp.prev, inp.cur, self.time, dt)
        self.player.update(dt)
        self.shake = max(0.0, self.shake - dt * 1.6)
        self.flash = max(0.0, self.flash - dt * 2.2)
        self.miss_flash = max(0.0, self.miss_flash - dt * 2.5)
        self.life_pulse = max(0.0, self.life_pulse - dt * 2.0)

        if not self.ending:
            cfg, d = S.DIFFICULTY[self.settings.difficulty], self._progress()
            self.spawn_timer -= dt
            if self.spawn_timer <= 0:
                self._spawn_wave()
                self.spawn_timer = lerp(*cfg["interval"], d) * random.uniform(0.85, 1.2)
            for item in self.spawn_queue:
                item[0] -= dt
            for delay, is_bomb, gravity in [q for q in self.spawn_queue if q[0] <= 0]:
                kind = None if is_bomb else random.choice(list(S.FRUITS))
                self.objects.append(self._launch(kind, gravity))
            self.spawn_queue = [q for q in self.spawn_queue if q[0] > 0]

            # --- blade collision: swept segment (previous -> current fingertip) vs. every object
            if self.blade.segment:
                a, b = self.blade.segment
                for obj in self.objects:
                    if obj.is_sliced:
                        continue                                   # never slice the same object twice
                    if segment_hits_circle(a, b, (obj.pos.x, obj.pos.y), obj.hit_radius()):
                        if isinstance(obj, Bomb):
                            self._explode(obj)
                            break
                        self._slice(obj)

        # --- physics
        for obj in self.objects:
            obj.update(dt)
        for half in self.halves:
            half.update(dt)
        self.particles.update(dt)
        self.halves = [h for h in self.halves if not h.gone]

        survivors = []
        for obj in self.objects:
            if obj.is_sliced:
                continue
            if obj.is_missed():
                if isinstance(obj, Fruit) and not self.ending:
                    self._lose_life(obj)
                continue
            survivors.append(obj)
        self.objects = survivors

        if self.ending:
            self.ending_timer -= dt
            if self.ending_timer <= 0:
                self.finish_game()

    def _slice(self, fruit: Fruit) -> None:
        fruit.is_sliced = True
        direction = self.blade.direction()
        self.halves.extend(fruit.make_halves(direction, self.blade.speed))
        self.particles.juice_burst(fruit.pos.x, fruit.pos.y, fruit.juice, direction)
        points, mult = self.player.register_slice(fruit.score_value)
        color = S.GOLD if mult > 1 else S.WHITE
        self.particles.add_text(f"+{points}", fruit.pos.x, fruit.pos.y - 20, self.fonts.get(30 + 4 * mult), color)
        self.audio.play("slice")
        if self.player.combo >= 2:
            self.audio.play_combo(self.player.combo)

    def _explode(self, bomb: Bomb) -> None:
        bomb.is_sliced = True
        self.particles.explosion(bomb.pos.x, bomb.pos.y)
        self.audio.play("bomb")
        self.shake, self.flash = 1.0, 1.0
        self.ending, self.ending_timer, self.ending_reason = True, 1.5, "bomb"

    def _lose_life(self, fruit: Fruit) -> None:
        self.player.lose_life()
        self.miss_flash = 1.0
        self.life_pulse = 1.0
        self.audio.play("miss")
        if self.player.lives <= 0:
            self.ending, self.ending_timer, self.ending_reason = True, 0.9, "lives"

    # ================================================================== drawing
    def draw(self) -> None:
        c = self.canvas
        st = self.state
        if st in (State.MENU, State.SETTINGS):
            c.blit(self.background, (0, 0))
            for f in self.menu_fruits:
                f.draw(c)
            c.blit(self.vignette, (0, 0))
            self._draw_menu() if st == State.MENU else self._draw_settings()
        elif st == State.CALIBRATION:
            self._draw_calibration()
        else:
            self._draw_world()
            c.blit(self.vignette, (0, 0))
            self._draw_hud()
            if st == State.PAUSED:
                self._draw_pause()
            elif st == State.GAME_OVER:
                self._draw_game_over()
        self._draw_toast()
        if self.debug:
            info = f"FPS {self.clock.get_fps():.0f}"
            if self.vision:
                info += f"  | vision {self.vision.snapshot().fps:.0f} fps | hands {self.vision.snapshot().num_hands}"
            draw_text(c, info, self.fonts.get(18), S.LIME, (10, H - 10), "bottomleft")

    def present(self) -> None:
        screen = pygame.display.get_surface()
        sw, sh = screen.get_size()
        ox = oy = 0
        if self.shake > 0:
            amp = 18 * self.shake ** 1.5
            ox, oy = int(random.uniform(-amp, amp)), int(random.uniform(-amp, amp))
        if (sw, sh) == (W, H):
            self._view = (0, 0, 1.0)
            if ox or oy:
                screen.fill((0, 0, 0))
            screen.blit(self.canvas, (ox, oy))
        else:  # fallback path when pygame.SCALED is unavailable: letterbox manually
            scale = min(sw / W, sh / H)
            size = (max(1, int(W * scale)), max(1, int(H * scale)))
            scaled = pygame.transform.smoothscale(self.canvas, size)
            screen.fill((0, 0, 0))
            px, py = (sw - size[0]) // 2, (sh - size[1]) // 2
            self._view = (px, py, scale)
            screen.blit(scaled, (px + ox, py + oy))
        pygame.display.flip()

    # ---------------------------------------------------------------- camera layer
    def _camera_surface(self, snap, factor: float) -> Optional[pygame.Surface]:
        if snap is None or snap.frame_rgb is None:
            return None
        key = (snap.frame_id, round(factor, 2))
        if self._cam_cache[0] == key:
            return self._cam_cache[1]
        frame = snap.frame_rgb
        if factor < 0.999:
            frame = cv2.convertScaleAbs(frame, alpha=factor)
        h, w = frame.shape[:2]
        surf = pygame.image.frombuffer(frame.tobytes(), (w, h), "RGB")
        surf = pygame.transform.smoothscale(surf, (W, H)).convert()
        self._cam_cache = (key, surf)
        return surf

    def _draw_hand(self, pts, strong: bool) -> None:
        c = self.canvas
        col = (80, 235, 255)
        for a, b in HAND_CONNECTIONS:
            pygame.draw.line(c, col, pts[a], pts[b], 4 if strong else 2)
        for i, p in enumerate(pts):
            pygame.draw.circle(c, (255, 255, 255), p, 5 if strong else 3)
        tip = pts[8]
        g = get_glow(44, S.MAGENTA, 1.0)
        c.blit(g, (tip[0] - g.get_width() / 2, tip[1] - g.get_height() / 2), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.circle(c, S.MAGENTA, tip, 9)
        pygame.draw.circle(c, (255, 255, 255), tip, 9, 2)

    def _draw_background(self) -> None:
        c = self.canvas
        if self.mode == "camera" and isinstance(self.input, CameraInput):
            mode = self.settings.camera_background
            snap = self.input.snapshot
            if mode == "Black":
                c.fill((0, 0, 0))
                pts = self.input.hand_screen_points()
                if pts and self.input.hand_detected:
                    self._draw_hand(pts, True)
                return
            surf = self._camera_surface(snap, 1.0 if mode == "Normal" else S.DARKEN_FACTOR)
            if surf is not None:
                c.blit(surf, (0, 0))
                return
        c.blit(self.background, (0, 0))

    def _draw_world(self) -> None:
        c = self.canvas
        self._draw_background()
        self.particles.draw_background_layer(c)
        for h in self.halves:
            h.draw(c)
        for o in self.objects:
            o.draw(c)
        self.particles.draw(c)
        self.blade.draw(c, self.time)
        # cursor ring so you always see where the blade tip is, even when not moving
        inp = self.input
        if self.state == State.PLAYING and not self.ending:
            vis, pos = (inp.tracker.visible, (inp.tracker.current_x, inp.tracker.current_y)) \
                if isinstance(inp, CameraInput) else (pygame.mouse.get_focused(), self._mouse_pos())
            if vis:
                pygame.draw.circle(c, (255, 255, 255), (int(pos[0]), int(pos[1])), 9, 2)
                pygame.draw.circle(c, S.CYAN, (int(pos[0]), int(pos[1])), 4)
        if self.flash > 0:
            fl = pygame.Surface((W, H))
            fl.fill((255, 235, 200))
            fl.set_alpha(int(220 * self.flash))
            c.blit(fl, (0, 0))
        if self.miss_flash > 0:
            edge = pygame.Surface((W, 90), pygame.SRCALPHA)
            for i in range(90):
                edge.fill((255, 40, 60, int(110 * self.miss_flash * (i / 90) ** 2)), pygame.Rect(0, i, W, 1))
            c.blit(edge, (0, H - 90))

    # ---------------------------------------------------------------- HUD
    def _draw_hud(self) -> None:
        c, f = self.canvas, self.fonts
        draw_text(c, "SCORE", f.get(20), S.GREY, (36, 22), "topleft")
        draw_text(c, f"{self.player.score:05d}", f.get(56), S.WHITE, (34, 42), "topleft", glow=S.CYAN)
        draw_text(c, f"BEST {max(self.player.best_score, self.player.score):05d}", f.get(20), S.GREY, (36, 108), "topleft")
        for i in range(S.START_LIVES):
            alive = i < self.player.lives
            pulse = self.life_pulse if i == self.player.lives else 0.0
            draw_heart(c, W - 50 - i * 52, 52, 24, alive, pulse if alive else pulse * 0.5)
        pl = self.player
        if pl.combo >= 2 and pl.combo_flash > 0:
            t = pl.combo_flash / 0.9
            scale = 1.0 + 0.45 * max(0.0, t - 0.7) / 0.3
            draw_text(c, f"COMBO ×{min(pl.combo, 99)}", f.get(54), S.GOLD, (W // 2, 120),
                      scale=scale, alpha=int(255 * min(1.0, t * 2.5)))
        elif pl.combo >= 2:
            draw_text(c, f"COMBO ×{pl.combo}", f.get(40), S.GOLD, (W // 2, 120), alpha=200)
        if self.mode == "camera" and isinstance(self.input, CameraInput) and self.state == State.PLAYING \
                and not self.input.tracker.visible:
            a = int(140 + 100 * math.sin(self.time * 5))
            draw_text(c, "Show your hand to the camera", f.get(28), S.GOLD, (W // 2, H - 50), alpha=max(60, a))

    # ---------------------------------------------------------------- menus
    def _draw_menu(self) -> None:
        c, f = self.canvas, self.fonts
        bob = math.sin(pygame.time.get_ticks() / 700) * 5
        draw_text(c, "SLICECAM", f.get(104), S.WHITE, (W // 2, 140 + bob), glow=S.CYAN)
        draw_text(c, "F R U I T   S L I C E R", f.get(26), S.MAGENTA, (W // 2, 214 + bob), glow=S.MAGENTA)
        for b in self.buttons[State.MENU]:
            b.draw(c, f)
        draw_text(c, f"Best score: {self.settings.best_score}", f.get(22), S.GREY, (W // 2, 628))
        draw_text(c, "Camera Mode: your index finger is the blade   •   Mouse Mode: great for testing",
                  f.get(18, False), S.GREY, (W // 2, H - 26))

    def _draw_settings(self) -> None:
        c, f = self.canvas, self.fonts
        draw_text(c, "SETTINGS", f.get(60), S.WHITE, (W // 2, 90), glow=S.MAGENTA)
        for b in self.buttons[State.SETTINGS]:
            b.draw(c, f)
        draw_text(c, "Click an option to change it", f.get(18, False), S.GREY, (W // 2, H - 26))

    def _draw_pause(self) -> None:
        c, f = self.canvas, self.fonts
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((4, 6, 18, 175))
        c.blit(dim, (0, 0))
        draw_text(c, "PAUSED", f.get(84), S.WHITE, (W // 2, 200), glow=S.CYAN)
        for b in self.buttons[State.PAUSED]:
            b.draw(c, f)
        draw_text(c, "ESC resume   •   R restart", f.get(18, False), S.GREY, (W // 2, H - 26))

    def _draw_game_over(self) -> None:
        c, f = self.canvas, self.fonts
        dim = pygame.Surface((W, H), pygame.SRCALPHA)
        dim.fill((4, 4, 14, 190))
        c.blit(dim, (0, 0))
        panel(c, pygame.Rect(W // 2 - 300, 110, 600, 340), border=S.RED)
        draw_text(c, "GAME OVER", f.get(76), S.RED, (W // 2, 180), glow=S.RED)
        draw_text(c, f"Final Score: {self.player.score}", f.get(40), S.WHITE, (W // 2, 285))
        draw_text(c, f"Best Score: {self.settings.best_score}", f.get(32), S.GOLD if self.new_best else S.GREY, (W // 2, 340))
        if self.new_best:
            draw_text(c, "NEW BEST!", f.get(26), S.LIME, (W // 2, 392), glow=S.LIME)
        else:
            reason = "Boom! You hit a bomb." if self.ending_reason == "bomb" else "You dropped too many fruits."
            draw_text(c, reason, f.get(22, False), S.GREY, (W // 2, 392))
        for b in self.buttons[State.GAME_OVER]:
            b.draw(c, f)

    def _draw_toast(self) -> None:
        text, t = self.toast
        if t > 0:
            draw_text(self.canvas, text, self.fonts.get(26), S.WHITE, (W // 2, H - 90), alpha=int(255 * min(1, t * 2)))

    # ---------------------------------------------------------------- calibration
    def _draw_calibration(self) -> None:
        c, f = self.canvas, self.fonts
        vis = self.vision
        c.blit(self.background, (0, 0))
        if vis is None:
            return
        status = vis.status
        if status == "error":
            self._draw_camera_error()
            return
        inp: CameraInput = self.input  # type: ignore
        snap = inp.snapshot
        surf = self._camera_surface(snap, 0.55)
        if surf is not None:
            c.blit(surf, (0, 0))
        c.blit(self.vignette, (0, 0))
        pts = inp.hand_screen_points()
        detected = inp.hand_detected
        if pts and detected:
            self._draw_hand(pts, True)

        panel(c, pygame.Rect(W // 2 - 330, 30, 660, 250), alpha=185)
        draw_text(c, "CAMERA MODE", f.get(48), S.WHITE, (W // 2, 70), glow=S.CYAN)
        for i, line in enumerate(["Show your hand to the camera.", "Raise your index finger.",
                                  "Move it around the screen."]):
            draw_text(c, line, f.get(26, False), S.WHITE, (W // 2, 122 + i * 34))
        if status == "starting" or snap.frame_rgb is None:
            draw_text(c, "Starting camera...", f.get(30), S.GOLD, (W // 2, 232))
        elif detected:
            label = snap.hand.label if snap.hand else ""
            r = draw_text(c, f"Hand detected  ({label} hand)", f.get(28), S.LIME, (W // 2 - 14, 232), glow=S.LIME)
            cx0, cy0 = r.right + 22, r.centery + 2          # hand-drawn check mark (font-independent)
            pygame.draw.lines(c, S.LIME, False, [(cx0 - 10, cy0), (cx0 - 3, cy0 + 8), (cx0 + 10, cy0 - 9)], 4)
            if snap.num_hands > 1:
                draw_text(c, "2 hands visible - tracking one consistently", f.get(18, False), S.GREY, (W // 2, 264))
        else:
            draw_text(c, "Looking for a hand...", f.get(28), S.GOLD, (W // 2, 232))
            if vis.warning:
                draw_text(c, "Tracking error: " + vis.warning[:80], f.get(16, False), S.RED, (W // 2, 264))
        if detected and status == "running":
            a = int(180 + 75 * math.sin(pygame.time.get_ticks() / 250))
            draw_text(c, "Press SPACE to start", f.get(34), S.WHITE, (W // 2, H - 110), glow=S.CYAN, alpha=a)
        elif self.calib_msg_timer > 0:
            draw_text(c, "A hand must be detected first", f.get(30), S.RED, (W // 2, H - 110))
        else:
            draw_text(c, "Tip: good lighting and a plain background help tracking", f.get(20, False), S.GREY,
                      (W // 2, H - 110))
        for b in self.buttons[State.CALIBRATION]:
            b.draw(c, f)
        draw_text(c, "If your movement feels reversed, press M to flip the camera", f.get(18, False), S.GREY,
                  (W // 2, H - 22))

    def _draw_camera_error(self) -> None:
        c, f = self.canvas, self.fonts
        v = self.vision
        camera_problem = v is None or v.error_source == "camera"
        panel(c, pygame.Rect(W // 2 - 440, 70, 880, 500), border=S.RED)
        if camera_problem:
            draw_text(c, "Camera could not be accessed.", f.get(42), S.RED, (W // 2, 120))
            lines = ["Check that:", "- your webcam is connected", "- another application isn't using it",
                     "- camera permissions are enabled"]
        else:
            draw_text(c, "Hand tracking could not start.", f.get(42), S.RED, (W // 2, 120))
            lines = ["The camera works, but MediaPipe failed to load.", "Try (in cmd, venv active):",
                     "- pip uninstall -y mediapipe",
                     "- pip install mediapipe==0.10.14",
                     "- if it still fails: install the Visual C++ Redistributable (x64)"]
        for i, line in enumerate(lines):
            draw_text(c, line, f.get(24, False), S.GOLD if i == 0 else S.WHITE, (W // 2 - 400, 180 + i * 36), "midleft")
        detail = (v.error if v else "") or ""
        for i, row in enumerate(textwrap.wrap(detail, 85)[:5]):
            draw_text(c, row, f.get(17, False), S.GREY, (W // 2 - 400, 410 + i * 24), "midleft")
        draw_text(c, "Details are also saved to slicecam_log.txt", f.get(16, False), S.GREY, (W // 2, 535))
        for b in self.camera_error_buttons:
            b.draw(c, f)
