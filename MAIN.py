import cv2
import mediapipe as mp
import numpy as np
import mouse
import tkinter as tk
import time
from collections import deque

# ─────────────────────────────────────────
#  SCREEN SIZE
# ─────────────────────────────────────────
root = tk.Tk()
SCREEN_W = root.winfo_screenwidth()
SCREEN_H = root.winfo_screenheight()
root.destroy()

# ─────────────────────────────────────────
#  CONFIG  (tweak these to taste)
# ─────────────────────────────────────────
FRAME_W, FRAME_H = 720, 520

ROI_LEFT,  ROI_TOP    = 180, 80
ROI_RIGHT, ROI_BOTTOM = 520, 420

# Smoothing
EMA_ALPHA         = 0.25    # lower → smoother but more lag (0.10-0.40)
VELOCITY_SMOOTH   = 0.30    # velocity EMA (damps oscillation)
DEAD_ZONE_PX      = 4       # ignore sub-pixel jitter in ROI coords
HISTORY_LEN       = 5       # frames kept for velocity calc

# Speed scaling (pixels/sec → multiplier)
SPEED_MIN_MULT    = 0.6     # slow hand → precision mode
SPEED_MAX_MULT    = 2.2     # fast hand → turbo mode
SPEED_THRESHOLD   = 60      # px/s that triggers turbo

# Gesture thresholds (fraction of hand width for normalisation)
PINCH_CLOSE       = 0.22    # pinch ON
PINCH_OPEN        = 0.30    # pinch OFF (hysteresis)
CLICK_DELAY       = 0.55    # seconds between clicks
SCROLL_SENSITIVITY= 0.8     # scroll lines per pixel

# EAR (Eye Aspect Ratio) – eye-open gate
EAR_THRESHOLD     = 0.18

# ─────────────────────────────────────────
#  UTILS
# ─────────────────────────────────────────
def euclidean(p1, p2):
    return float(np.linalg.norm(np.array(p1, dtype=float) - np.array(p2, dtype=float)))

def roi_to_screen(rx, ry):
    """Map a point inside the ROI to screen coordinates."""
    nx = (rx - ROI_LEFT)  / (ROI_RIGHT  - ROI_LEFT)
    ny = (ry - ROI_TOP)   / (ROI_BOTTOM - ROI_TOP)
    return np.clip(nx, 0, 1) * SCREEN_W, np.clip(ny, 0, 1) * SCREEN_H

# ─────────────────────────────────────────
#  KALMAN FILTER  (4-state: x, y, vx, vy)
# ─────────────────────────────────────────
def make_kalman():
    kf = cv2.KalmanFilter(4, 2)
    kf.measurementMatrix  = np.array([[1,0,0,0],[0,1,0,0]], np.float32)
    kf.transitionMatrix   = np.array([[1,0,1,0],
                                      [0,1,0,1],
                                      [0,0,1,0],
                                      [0,0,0,1]], np.float32)
    kf.processNoiseCov    = np.eye(4, dtype=np.float32) * 0.01
    kf.measurementNoiseCov= np.eye(2, dtype=np.float32) * 0.5
    kf.errorCovPost       = np.eye(4, dtype=np.float32)
    return kf

kalman = make_kalman()

# ─────────────────────────────────────────
#  MEDIAPIPE
# ─────────────────────────────────────────
mp_hands = mp.solutions.hands
mp_face  = mp.solutions.face_mesh
mp_draw  = mp.solutions.drawing_utils

hands     = mp_hands.Hands(max_num_hands=1,
                            min_detection_confidence=0.75,
                            min_tracking_confidence=0.75)
face_mesh = mp_face.FaceMesh(refine_landmarks=True,
                              min_detection_confidence=0.5,
                              min_tracking_confidence=0.5)

# ─────────────────────────────────────────
#  STATE
# ─────────────────────────────────────────
cam = cv2.VideoCapture(0)
cam.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_W)
cam.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
cam.set(cv2.CAP_PROP_FPS, 60)

# Smoothed cursor position (screen coords)
cursor_x, cursor_y   = SCREEN_W / 2, SCREEN_H / 2

# EMA position (ROI coords before screen mapping)
ema_x, ema_y         = None, None

# Velocity EMA (screen coords/sec)
vel_x, vel_y         = 0.0, 0.0
prev_time            = time.time()
pos_history          = deque(maxlen=HISTORY_LEN)  # (time, sx, sy)

# Gesture states with hysteresis
lclick_active        = False
rclick_active        = False
scroll_active        = False
scroll_ref_y         = None
last_click_time      = 0.0
last_lclick_down     = 0.0   # for double-click detection
double_click_window  = 0.4

gesture_label        = "IDLE"
eye_valid            = False


# ─────────────────────────────────────────
#  HELPER: get normalised distance (hand-size aware)
# ─────────────────────────────────────────
def hand_scale(hand_lms, w, h):
    """Approximate hand width from wrist→index_mcp for normalisation."""
    wrist = hand_lms.landmark[mp_hands.HandLandmark.WRIST]
    mcp   = hand_lms.landmark[mp_hands.HandLandmark.INDEX_FINGER_MCP]
    px1   = (wrist.x * w, wrist.y * h)
    px2   = (mcp.x   * w, mcp.y   * h)
    return max(euclidean(px1, px2), 1.0)

def get_px(lm_id, hand_lms, w, h):
    lm = hand_lms.landmark[lm_id]
    x  = int(lm.x * w)
    y  = int(lm.y * h)
    if 0 <= x < w and 0 <= y < h:
        return (x, y)
    return None


# ─────────────────────────────────────────
#  DRAW HELPERS
# ─────────────────────────────────────────
FONT = cv2.FONT_HERSHEY_SIMPLEX

def draw_roi(frame):
    overlay = frame.copy()
    cv2.rectangle(overlay, (ROI_LEFT, ROI_TOP), (ROI_RIGHT, ROI_BOTTOM),
                  (0, 120, 255), -1)
    cv2.addWeighted(overlay, 0.08, frame, 0.92, 0, frame)
    cv2.rectangle(frame, (ROI_LEFT, ROI_TOP), (ROI_RIGHT, ROI_BOTTOM),
                  (0, 180, 255), 2)
    cv2.putText(frame, "CONTROL ZONE", (ROI_LEFT + 4, ROI_TOP - 8),
                FONT, 0.45, (0, 180, 255), 1)

def draw_hud(frame, gesture, eye_ok, fps):
    bar_h = 50
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (FRAME_W, bar_h), (10, 10, 10), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    eye_col = (0, 220, 100) if eye_ok else (0, 60, 200)
    cv2.putText(frame, f"EYE: {'OK' if eye_ok else 'CLOSED'}", (14, 33),
                FONT, 0.75, eye_col, 2)

    gcolors = {"IDLE": (180,180,180), "LEFT_CLICK": (50,220,50),
               "RIGHT_CLICK": (50,120,255), "SCROLL": (255,200,0),
               "DOUBLE_CLICK": (0,255,200)}
    gcol = gcolors.get(gesture, (200,200,200))
    cv2.putText(frame, f"GESTURE: {gesture}", (180, 33),
                FONT, 0.75, gcol, 2)

    cv2.putText(frame, f"FPS:{fps:3d}", (FRAME_W - 100, 33),
                FONT, 0.7, (160,160,160), 1)

def draw_fingertip(frame, pt, color=(0,255,200), r=10):
    if pt:
        cv2.circle(frame, pt, r,     color,          -1)
        cv2.circle(frame, pt, r + 3, (*color[:2], 80), 1)


# ─────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────
fps_counter, fps_t0, fps_display = 0, time.time(), 0

while True:
    ret, frame = cam.read()
    if not ret:
        break

    frame = cv2.flip(frame, 1)
    frame = cv2.resize(frame, (FRAME_W, FRAME_H))
    h, w  = frame.shape[:2]
    rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    now   = time.time()

    # ── FPS ──────────────────────────────
    fps_counter += 1
    if now - fps_t0 >= 1.0:
        fps_display = fps_counter
        fps_counter, fps_t0 = 0, now

    # ═════════════════════════════════════
    #  EYE GATE  (face mesh EAR)
    # ═════════════════════════════════════
    eye_valid = False
    face_res  = face_mesh.process(rgb)
    if face_res.multi_face_landmarks:
        face = face_res.multi_face_landmarks[0]
        lm   = face.landmark
        def lmxy(idx): return (lm[idx].x * w, lm[idx].y * h)

        l_top    = lmxy(159); l_bot = lmxy(145)
        l_left   = lmxy(33);  l_right = lmxy(133)
        vertical = euclidean(l_top, l_bot)
        horiz    = euclidean(l_left, l_right)
        if horiz > 0 and vertical / horiz > EAR_THRESHOLD:
            eye_valid = True

    # ═════════════════════════════════════
    #  HAND TRACKING
    # ═════════════════════════════════════
    hand_res = hands.process(rgb)
    gesture_label = "IDLE"

    draw_roi(frame)

    if hand_res.multi_hand_landmarks and eye_valid:
        hand = hand_res.multi_hand_landmarks[0]
        scale = hand_scale(hand, w, h)   # hand-size normalisation

        # ── Key landmarks ────────────────
        index_tip  = get_px(mp_hands.HandLandmark.INDEX_FINGER_TIP,  hand, w, h)
        middle_tip = get_px(mp_hands.HandLandmark.MIDDLE_FINGER_TIP, hand, w, h)
        thumb_tip  = get_px(mp_hands.HandLandmark.THUMB_TIP,         hand, w, h)
        pinky_tip  = get_px(mp_hands.HandLandmark.PINKY_TIP,         hand, w, h)
        ring_tip   = get_px(mp_hands.HandLandmark.RING_FINGER_TIP,   hand, w, h)

        # ── Mouse movement (index fingertip) ──
        if index_tip:
            rx = np.clip(index_tip[0], ROI_LEFT,  ROI_RIGHT)
            ry = np.clip(index_tip[1], ROI_TOP,   ROI_BOTTOM)

            # 1) Kalman correction
            meas   = np.array([[np.float32(rx)], [np.float32(ry)]])
            kalman.correct(meas)
            pred   = kalman.predict()
            kx, ky = float(pred[0]), float(pred[1])

            # 2) Dead-zone: skip tiny movements
            if ema_x is None:
                ema_x, ema_y = kx, ky

            dx_raw = kx - ema_x
            dy_raw = ky - ema_y
            if abs(dx_raw) < DEAD_ZONE_PX: dx_raw = 0
            if abs(dy_raw) < DEAD_ZONE_PX: dy_raw = 0

            # 3) EMA smoothing on ROI coords
            ema_x += EMA_ALPHA * dx_raw
            ema_y += EMA_ALPHA * dy_raw

            # 4) Map to screen
            target_sx, target_sy = roi_to_screen(ema_x, ema_y)

            # 5) Velocity-adaptive blending
            dt = now - prev_time if now > prev_time else 0.016
            if pos_history:
                pt = pos_history[-1]
                raw_vx = (target_sx - pt[1]) / max(dt, 0.001)
                raw_vy = (target_sy - pt[2]) / max(dt, 0.001)
                vel_x  = VELOCITY_SMOOTH * raw_vx + (1 - VELOCITY_SMOOTH) * vel_x
                vel_y  = VELOCITY_SMOOTH * raw_vy + (1 - VELOCITY_SMOOTH) * vel_y

            speed  = np.hypot(vel_x, vel_y)
            t      = min(speed / SPEED_THRESHOLD, 1.0)
            mult   = SPEED_MIN_MULT + t * (SPEED_MAX_MULT - SPEED_MIN_MULT)

            # 6) Lerp cursor toward target (final smoothing layer)
            blend  = min(EMA_ALPHA * mult, 1.0)
            cursor_x_new = cursor_x + blend * (target_sx - cursor_x)
            cursor_y_new = cursor_y + blend * (target_sy - cursor_y)

            cursor_x, cursor_y = cursor_x_new, cursor_y_new
            mouse.move(int(cursor_x), int(cursor_y))
            pos_history.append((now, target_sx, target_sy))
            prev_time = now

            # Draw fingertip
            draw_fingertip(frame, index_tip)

        # ── Normalised distances ──────────
        def nd(p1, p2):
            if p1 and p2: return euclidean(p1, p2) / scale
            return 999.0

        d_thumb_index  = nd(thumb_tip, index_tip)
        d_thumb_middle = nd(thumb_tip, middle_tip)
        d_thumb_pinky  = nd(thumb_tip, pinky_tip)
        d_index_middle = nd(index_tip, middle_tip)

        current_time = now

        # ── SCROLL: index + middle tips close together, thumb away ──
        if (d_index_middle < PINCH_CLOSE * 1.2
                and d_thumb_index > PINCH_OPEN):
            if not scroll_active:
                scroll_active  = True
                scroll_ref_y   = index_tip[1] if index_tip else 0
                gesture_label  = "SCROLL"
            else:
                if index_tip:
                    delta = (index_tip[1] - scroll_ref_y) * SCROLL_SENSITIVITY
                    if abs(delta) > 2:
                        mouse.wheel(-delta / 20)
                        scroll_ref_y = index_tip[1]
                gesture_label = "SCROLL"
        else:
            scroll_active = False

            # ── LEFT CLICK: thumb + index ──────────────────────────────
            if d_thumb_index < PINCH_CLOSE:
                if not lclick_active and (current_time - last_click_time > CLICK_DELAY):
                    # double-click detection
                    if current_time - last_lclick_down < double_click_window:
                        mouse.double_click()
                        gesture_label = "DOUBLE_CLICK"
                    else:
                        mouse.click('left')
                        gesture_label = "LEFT_CLICK"
                    last_lclick_down = current_time
                    last_click_time  = current_time
                    lclick_active    = True
                else:
                    gesture_label = "LEFT_CLICK"
            elif d_thumb_index > PINCH_OPEN:
                lclick_active = False

            # ── RIGHT CLICK: thumb + pinky ────────────────────────────
            if (d_thumb_pinky < PINCH_CLOSE
                    and d_thumb_index > PINCH_OPEN
                    and not rclick_active
                    and current_time - last_click_time > CLICK_DELAY):
                mouse.click('right')
                gesture_label   = "RIGHT_CLICK"
                last_click_time = current_time
                rclick_active   = True
            elif d_thumb_pinky > PINCH_OPEN:
                rclick_active = False

        # Draw hand skeleton
        mp_draw.draw_landmarks(frame, hand, mp_hands.HAND_CONNECTIONS,
            mp_draw.DrawingSpec(color=(80,80,80),  thickness=1, circle_radius=2),
            mp_draw.DrawingSpec(color=(200,200,0), thickness=2))

        # Highlight active fingertips
        if thumb_tip:  draw_fingertip(frame, thumb_tip,  (255,120,50),  7)
        if pinky_tip:  draw_fingertip(frame, pinky_tip,  (200,50,255),  7)
        if middle_tip: draw_fingertip(frame, middle_tip, (50,200,255),  7)

    elif not eye_valid and hand_res.multi_hand_landmarks:
        cv2.putText(frame, "! Open your eyes to enable mouse !",
                    (ROI_LEFT, FRAME_H - 20), FONT, 0.6, (0,60,255), 2)

    # ── HUD ──────────────────────────────
    draw_hud(frame, gesture_label, eye_valid, fps_display)

    cv2.imshow("Air Mouse v2 | ESC to quit", frame)
    if cv2.waitKey(1) & 0xFF == 27:
        break

cam.release()
cv2.destroyAllWindows()