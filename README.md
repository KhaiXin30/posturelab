# Posture Flower

The **Posture Flower** is a desktop companion that provides physical feedback when a user has poor posture while studying or working at a computer.

A camera detects the user's posture using **MediaPipe**. The Python program classifies the posture and sends commands through USB serial to a **Raspberry Pi Pico W**, which controls five servo motors.

## System Overview

```text
Camera
   ↓
Laptop
Python + OpenCV + MediaPipe
   ↓
Posture classification
   ↓
USB Serial
   ↓
Raspberry Pi Pico W
   ↓
5 Servo Motors
   ↓
Stem + Flower Petals
```

## Flower Behavior

| Posture State | Physical Response |
|---|---|
| Good posture | Stem upright, petals open |
| Bad posture | Stem bends |
| Prolonged bad posture | Stem bends further and petals close |
| Good posture restored | Stem returns upright and petals reopen |

Current timing:

```text
Bad posture > 1.5 s
→ Stem bends

Bad posture > 8 s
→ Stem bends further and petals close

Good posture > 3 s
→ Stem returns upright and petals reopen
```

---

# Hardware

## Servo Connections

```text
Servo 1 → Stem tendon 1 → GP15
Servo 2 → Stem tendon 2 → GP14
Servo 3 → Stem tendon 3 → GP13
Servo 4 → Inner petal string → GP12
Servo 5 → Outer petal / sliding collar string → GP11
```

Servos 1–3 control stem bending.

Servo 4 tightens the inner petal string to close the flower.

Servo 5 controls the outer string connected to the sliding collar.

## Servo Power

Do **not** power the servo motors from the Pico W 3.3 V pin.

Use a separate regulated 5 V power supply.

```text
External 5 V + → Servo power

External GND → Servo GND
                  ↑
Pico GND ─────────┘

Pico GPIO → Servo signal
```

The Pico and servo power supply must share a common ground.

---

# Software Requirements

Install:

- Python 3
- Arduino IDE
- OpenCV
- MediaPipe
- pySerial

---

# Python Setup

Open Terminal and go to the project folder:

```bash
cd posturelab
```

Create a virtual environment:

```bash
python3.13 -m venv posture_env
```

Activate it:

```bash
source posture_env/bin/activate
```

Install the required packages:

```bash
python -m pip install --upgrade pip
python -m pip install --no-compile -r requirements.txt
```

`--no-compile` works around a typo in a test file shipped inside mediapipe 1.2.2, which otherwise crashes `pip install`.

---

# MediaPipe Model

Place the MediaPipe Pose Landmarker model in the same folder as the Python script.

```text
posturelab/
├── posture_flower.py
├── camera_test.py
├── pose_landmarker_lite.task
└── posture_env/
```

The code expects:

```python
MODEL_PATH = "pose_landmarker_lite.task"
```

---

# Camera Setup

The system can use either:

- the laptop webcam
- Arducam B029202 USB camera

Select the camera in `posture_flower.py`:

```python
CAMERA_INDEX = 0
```

Usually:

```text
0 = laptop webcam
1 = external Arducam
```

The exact number may vary.

## Test the Camera

Run:

```bash
python camera_test.py
```

If the external camera does not open, try changing the camera index between:

```python
0
```

and:

```python
1
```

Make sure the camera can clearly see:

```text
ear
shoulder
hip
```

A side or three-quarter view works best for posture detection.

---

# Posture Calibration

Run:

```bash
python posture_flower.py
```

When the camera window opens:

1. Sit in your normal good posture.
2. Click the camera window.
3. Press `C`.
4. Stay still during calibration.

The program records the user's good posture as the baseline.

Current posture thresholds:

```python
HEAD_THRESHOLD = 0.10
TORSO_THRESHOLD = 5.0
```

Good posture is detected when:

```text
Head change < 0.10
AND
Torso change < 5°
```

Press:

```text
Q
```

to quit.

---

# Pico W Setup

Upload the Arduino servo-control code to the Raspberry Pi Pico W using Arduino IDE.

The Pico receives commands from Python in this format:

```text
S1,S2,S3,S4,S5
```

Example:

```text
60,0,0,45,45
```

Each number represents the target angle for one servo.

---

# Find the Pico Serial Port

Connect the Pico W to the laptop through USB.

Run:

```bash
python -m serial.tools.list_ports
```

Look for something similar to:

```text
/dev/cu.usbmodem1101
```

Then update this line in `posture_flower.py`:

```python
SERIAL_PORT = "/dev/cu.usbmodem1101"
```

The port number may change when the Pico is disconnected and reconnected.

---

# Enable Serial Control

In `posture_flower.py`, set:

```python
SERIAL_ENABLED = True
```

Before running the Python program, close:

- Arduino Serial Monitor
- Arduino Serial Plotter

Only one program can use the Pico serial port at a time.

Then run:

```bash
python posture_flower.py
```

The Terminal should show:

```text
Connected to Pico
```

When posture changes, Python sends the corresponding five-servo command to the Pico.

---

# Posture States

## Good Posture

```text
0,0,0,0,0
```

Result:

- Stem upright
- Petals open

## Bad Posture

After bad posture is maintained for approximately 1.5 seconds:

```text
45,0,0,0,0
```

Result:

- Stem bends
- Petals remain open

## Prolonged Bad Posture

After bad posture continues for approximately 8 seconds:

```text
60,0,0,45,45
```

Result:

- Stem bends further
- Servo 4 tightens the inner petal string
- Servo 5 releases the outer/sliding-collar string
- Petals close

## Recovery

After good posture is maintained for approximately 3 seconds:

```text
0,0,0,0,0
```

Result:

- Stem returns upright
- Petals reopen

---

# Controls

```text
C = Calibrate good posture
Q = Quit
```

---

# Running the System

1. Connect the Arducam or laptop camera.
2. Connect the Pico W through USB.
3. Power the servos using the external 5 V supply.
4. Make sure the Pico and servo supply share GND.
5. Close Arduino Serial Monitor.
6. Activate the Python environment:

```bash
source posture_env/bin/activate
```

7. Run:

```bash
python posture_flower.py
```

8. Sit in good posture and press `C`.
9. The flower will then respond automatically to changes in posture.