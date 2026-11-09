import cv2
import mediapipe as mp
import math
import time


# ============================================================
# USER SETTINGS
# ============================================================

MODEL_PATH = "pose_landmarker_lite.task"

# Camera:
# 1 = MacBook camera
# 0 = external Arducam
CAMERA_INDEX = 0

# Keep FALSE while you don't have the Pico
# Change to TRUE when Pico is connected
SERIAL_ENABLED = True

# Change this later to your actual Pico port
SERIAL_PORT = "/dev/cu.usbmodem1101"


BAUD_RATE = 9600


# ============================================================
# TIMING
# ============================================================

# Bad posture must continue before stem bends
BAD_CONFIRM_SECONDS = 1.5

# Bad posture must continue before petals close
PROLONGED_BAD_SECONDS = 8.0

# Good posture must continue before flower resets
RECOVERY_SECONDS = 3.0

# Frames used to learn your good posture
CALIBRATION_FRAMES = 60


# ============================================================
# POSTURE THRESHOLDS
# ============================================================

HEAD_THRESHOLD = 0.10
TORSO_THRESHOLD = 5.0


# ============================================================
# SERVO STATES
#
# S1-S3 = stem tendons
# S4    = inside petal tendon
# S5    = outside petal tendon
# ============================================================

# GOOD:
# Stem upright + flower open
GOOD_SERVOS = {
    "S1": 0,
    "S2": 0,
    "S3": 0,
    "S4": 0,
    "S5": 0
}

# BAD:
# Stem bends, flower stays open
BAD_SERVOS = {
    "S1": 45,
    "S2": 0,
    "S3": 0,
    "S4": 0,
    "S5": 0
}

# PROLONGED BAD:
# Stem bends more + petals close
PROLONGED_BAD_SERVOS = {
    "S1": 60,
    "S2": 0,
    "S3": 0,

    # S4 tightens inside tendon
    "S4": 45,

    # S5 should be wound/mounted in the opposite direction
    # so +45 causes the outside tendon to loosen
    "S5": 45
}


# ============================================================
# SERIAL SETUP
# ============================================================

ser = None

if SERIAL_ENABLED:

    import serial

    try:
        ser = serial.Serial(
            SERIAL_PORT,
            BAUD_RATE,
            timeout=1
        )

        time.sleep(2)

        print("Connected to Pico:", SERIAL_PORT)

    except Exception as e:

        print("Could not connect to Pico:")
        print(e)

        ser = None


# Remember what was last sent
last_sent_targets = None


def send_servo_targets(servos):

    global last_sent_targets

    # Don't repeatedly send the same command
    if servos == last_sent_targets:
        return

    command = (
        f"{servos['S1']},"
        f"{servos['S2']},"
        f"{servos['S3']},"
        f"{servos['S4']},"
        f"{servos['S5']}\n"
    )

    if SERIAL_ENABLED and ser is not None:

        ser.write(command.encode())

        print(
            "Sent to Pico:",
            command.strip()
        )

    else:

        print(
            "SIMULATED:",
            command.strip()
        )

    last_sent_targets = servos.copy()


# ============================================================
# MEDIAPIPE SETUP
# ============================================================

BaseOptions = mp.tasks.BaseOptions

PoseLandmarker = (
    mp.tasks.vision.PoseLandmarker
)

PoseLandmarkerOptions = (
    mp.tasks.vision.PoseLandmarkerOptions
)

RunningMode = (
    mp.tasks.vision.RunningMode
)


options = PoseLandmarkerOptions(

    base_options=BaseOptions(
        model_asset_path=MODEL_PATH
    ),

    running_mode=RunningMode.VIDEO,

    num_poses=1,

    min_pose_detection_confidence=0.5,

    min_pose_presence_confidence=0.5,

    min_tracking_confidence=0.5
)


# ============================================================
# CAMERA
# ============================================================

camera = cv2.VideoCapture(
    CAMERA_INDEX
)

if not camera.isOpened():

    print("ERROR: Cannot open camera")

    exit()


# ============================================================
# VARIABLES
# ============================================================

baseline_head = None
baseline_torso = None

calibrating = False
calibration_data = []

bad_start_time = None
good_start_time = None

current_state = "GOOD"

servo_targets = GOOD_SERVOS.copy()

flower_state = "UPRIGHT + OPEN"


# ============================================================
# POSTURE CALCULATION
# ============================================================

def calculate_posture(
    ear,
    shoulder,
    hip
):

    torso_length = math.sqrt(
        (shoulder.x - hip.x) ** 2
        +
        (shoulder.y - hip.y) ** 2
    )

    if torso_length < 0.001:

        return None, None


    # Head position relative to shoulder
    head_offset = (
        ear.x - shoulder.x
    ) / torso_length


    # Shoulder-to-hip angle
    torso_angle = math.degrees(

        math.atan2(

            shoulder.x - hip.x,

            hip.y - shoulder.y
        )
    )


    return (
        head_offset,
        torso_angle
    )


# ============================================================
# DRAW SERVO STATUS
# ============================================================

def draw_servo_status(
    frame,
    servos,
    start_y=245
):

    y = start_y

    for servo, angle in servos.items():

        cv2.putText(
            frame,
            f"{servo}: {angle} deg",
            (20, y),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.6,

            (255, 255, 255),

            2
        )

        y += 27


# ============================================================
# START
# ============================================================

with PoseLandmarker.create_from_options(
    options
) as landmarker:


    print("")
    print("==============================")
    print("POSTURE FLOWER")
    print("==============================")
    print("")
    print("C = Calibrate good posture")
    print("Q = Quit")
    print("")


    # Start everything at default
    send_servo_targets(
        GOOD_SERVOS
    )


    while True:

        success, frame = camera.read()

        if not success:

            print("Camera failed")

            break


        # ====================================================
        # MEDIAPIPE
        # ====================================================

        rgb_frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )


        mp_image = mp.Image(

            image_format=mp.ImageFormat.SRGB,

            data=rgb_frame
        )


        timestamp_ms = (
            time.monotonic_ns()
            // 1_000_000
        )


        result = landmarker.detect_for_video(

            mp_image,

            timestamp_ms
        )


        # ====================================================
        # DEFAULT DISPLAY VALUES
        # ====================================================

        posture_text = (
            "NO PERSON DETECTED"
        )

        head_change = None

        torso_change = None

        bad_duration = 0

        recovery_duration = 0


        # ====================================================
        # PERSON DETECTED
        # ====================================================

        if result.pose_landmarks:

            landmarks = (
                result.pose_landmarks[0]
            )


            # ------------------------------------------------
            # PICK LEFT OR RIGHT SIDE
            #
            # 7  left ear
            # 8  right ear
            # 11 left shoulder
            # 12 right shoulder
            # 23 left hip
            # 24 right hip
            # ------------------------------------------------

            left_visibility = (

                landmarks[7].visibility
                +
                landmarks[11].visibility
                +
                landmarks[23].visibility
            )


            right_visibility = (

                landmarks[8].visibility
                +
                landmarks[12].visibility
                +
                landmarks[24].visibility
            )


            if (
                left_visibility
                >=
                right_visibility
            ):

                ear = landmarks[7]

                shoulder = landmarks[11]

                hip = landmarks[23]


            else:

                ear = landmarks[8]

                shoulder = landmarks[12]

                hip = landmarks[24]


            # ------------------------------------------------
            # CALCULATE POSTURE
            # ------------------------------------------------

            head_offset, torso_angle = (
                calculate_posture(
                    ear,
                    shoulder,
                    hip
                )
            )


            if head_offset is not None:


                # ============================================
                # DRAW LANDMARKS
                # ============================================

                height, width, _ = (
                    frame.shape
                )


                ear_point = (

                    int(ear.x * width),

                    int(ear.y * height)
                )


                shoulder_point = (

                    int(shoulder.x * width),

                    int(shoulder.y * height)
                )


                hip_point = (

                    int(hip.x * width),

                    int(hip.y * height)
                )


                cv2.circle(
                    frame,
                    ear_point,
                    8,
                    (255, 255, 255),
                    -1
                )


                cv2.circle(
                    frame,
                    shoulder_point,
                    8,
                    (255, 255, 255),
                    -1
                )


                cv2.circle(
                    frame,
                    hip_point,
                    8,
                    (255, 255, 255),
                    -1
                )


                cv2.line(
                    frame,
                    ear_point,
                    shoulder_point,
                    (255, 255, 255),
                    2
                )


                cv2.line(
                    frame,
                    shoulder_point,
                    hip_point,
                    (255, 255, 255),
                    2
                )


                # ============================================
                # CALIBRATION
                # ============================================

                if calibrating:

                    calibration_data.append(
                        (
                            head_offset,
                            torso_angle
                        )
                    )


                    posture_text = (

                        "CALIBRATING "

                        f"{len(calibration_data)}"

                        f"/{CALIBRATION_FRAMES}"
                    )


                    if (
                        len(calibration_data)
                        >=
                        CALIBRATION_FRAMES
                    ):

                        baseline_head = sum(

                            value[0]

                            for value
                            in calibration_data

                        ) / len(
                            calibration_data
                        )


                        baseline_torso = sum(

                            value[1]

                            for value
                            in calibration_data

                        ) / len(
                            calibration_data
                        )


                        calibrating = False

                        bad_start_time = None

                        good_start_time = None

                        current_state = "GOOD"

                        servo_targets = (
                            GOOD_SERVOS.copy()
                        )

                        flower_state = (
                            "UPRIGHT + OPEN"
                        )


                        send_servo_targets(
                            servo_targets
                        )


                        print("")
                        print(
                            "Calibration complete"
                        )

                        print(
                            "Baseline head:",
                            round(
                                baseline_head,
                                3
                            )
                        )

                        print(
                            "Baseline torso:",
                            round(
                                baseline_torso,
                                2
                            )
                        )

                        print("")


                # ============================================
                # NORMAL POSTURE DETECTION
                # ============================================

                elif baseline_head is not None:


                    head_change = abs(

                        head_offset
                        -
                        baseline_head
                    )


                    torso_change = abs(

                        torso_angle
                        -
                        baseline_torso
                    )


                    posture_is_good = (

                        head_change
                        <
                        HEAD_THRESHOLD

                        and

                        torso_change
                        <
                        TORSO_THRESHOLD
                    )


                    # ========================================
                    # GOOD POSTURE
                    # ========================================

                    if posture_is_good:

                        posture_text = "GOOD"

                        # Stop accumulating bad time
                        bad_start_time = None


                        # Already good
                        if current_state == "GOOD":

                            good_start_time = None

                            servo_targets = (
                                GOOD_SERVOS.copy()
                            )

                            flower_state = (
                                "UPRIGHT + OPEN"
                            )


                        # Flower currently bent
                        else:

                            if good_start_time is None:

                                good_start_time = (
                                    time.monotonic()
                                )


                            recovery_duration = (

                                time.monotonic()
                                -
                                good_start_time
                            )


                            flower_state = (

                                "RECOVERING "

                                f"{recovery_duration:.1f}"

                                f"/{RECOVERY_SECONDS:.1f}s"
                            )


                            # -------------------------------
                            # GOOD FOR LONG ENOUGH
                            # -------------------------------

                            if (
                                recovery_duration
                                >=
                                RECOVERY_SECONDS
                            ):

                                current_state = "GOOD"

                                servo_targets = (
                                    GOOD_SERVOS.copy()
                                )

                                flower_state = (
                                    "UPRIGHT + OPEN"
                                )

                                good_start_time = None


                                send_servo_targets(
                                    servo_targets
                                )


                    # ========================================
                    # BAD POSTURE
                    # ========================================

                    else:

                        posture_text = "BAD"

                        # Cancel recovery
                        good_start_time = None


                        if bad_start_time is None:

                            bad_start_time = (
                                time.monotonic()
                            )


                        bad_duration = (

                            time.monotonic()
                            -
                            bad_start_time
                        )


                        # ------------------------------------
                        # BAD < 1.5 seconds
                        # ------------------------------------

                        if (
                            bad_duration
                            <
                            BAD_CONFIRM_SECONDS
                        ):

                            if current_state == "GOOD":

                                flower_state = (
                                    "CHECKING POSTURE..."
                                )


                        # ------------------------------------
                        # BAD
                        # STEM BENDS
                        # ------------------------------------

                        elif (
                            bad_duration
                            <
                            PROLONGED_BAD_SECONDS
                        ):

                            if current_state != "BAD":

                                current_state = "BAD"

                                servo_targets = (
                                    BAD_SERVOS.copy()
                                )

                                send_servo_targets(
                                    servo_targets
                                )


                            flower_state = (
                                "BENT + OPEN"
                            )


                        # ------------------------------------
                        # PROLONGED BAD
                        # STEM BENT + PETALS CLOSE
                        # ------------------------------------

                        else:

                            if (
                                current_state
                                !=
                                "PROLONGED_BAD"
                            ):

                                current_state = (
                                    "PROLONGED_BAD"
                                )

                                servo_targets = (
                                    PROLONGED_BAD_SERVOS.copy()
                                )

                                send_servo_targets(
                                    servo_targets
                                )


                            flower_state = (
                                "BENT + CLOSED"
                            )


                else:

                    posture_text = (
                        "PRESS C TO CALIBRATE"
                    )


        # ====================================================
        # DISPLAY
        # ====================================================

        cv2.putText(
            frame,
            f"POSTURE: {posture_text}",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2
        )


        if head_change is not None:

            cv2.putText(
                frame,

                f"HEAD CHANGE: "
                f"{head_change:.3f}",

                (20, 70),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.6,

                (255, 255, 255),

                2
            )


        if torso_change is not None:

            cv2.putText(
                frame,

                f"TORSO CHANGE: "
                f"{torso_change:.1f} deg",

                (20, 100),

                cv2.FONT_HERSHEY_SIMPLEX,

                0.6,

                (255, 255, 255),

                2
            )


        cv2.putText(
            frame,

            f"BAD TIME: "
            f"{bad_duration:.1f} s",

            (20, 135),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.6,

            (255, 255, 255),

            2
        )


        cv2.putText(
            frame,

            f"FLOWER: "
            f"{flower_state}",

            (20, 170),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.6,

            (255, 255, 255),

            2
        )


        cv2.putText(
            frame,

            f"STATE: "
            f"{current_state}",

            (20, 205),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.6,

            (255, 255, 255),

            2
        )


        draw_servo_status(
            frame,
            servo_targets
        )


        cv2.putText(
            frame,

            "C = calibrate | Q = quit",

            (20, frame.shape[0] - 20),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.55,

            (255, 255, 255),

            1
        )


        cv2.imshow(
            "Posture Flower Prototype",
            frame
        )


        # ====================================================
        # KEYBOARD
        # ====================================================

        key = (
            cv2.waitKey(1)
            &
            0xFF
        )


        if (
            key == ord("c")
            or
            key == ord("C")
        ):

            print("")
            print(
                "Sit in your GOOD posture."
            )

            print(
                "Calibration starting..."
            )

            print("")


            calibration_data = []

            calibrating = True

            baseline_head = None

            baseline_torso = None

            bad_start_time = None

            good_start_time = None

            current_state = "GOOD"

            servo_targets = (
                GOOD_SERVOS.copy()
            )

            flower_state = (
                "UPRIGHT + OPEN"
            )


            send_servo_targets(
                servo_targets
            )


        elif (
            key == ord("q")
            or
            key == ord("Q")
        ):

            break


# ============================================================
# CLEANUP
# ============================================================

camera.release()

cv2.destroyAllWindows()


if ser is not None:

    ser.close()