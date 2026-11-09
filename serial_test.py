import serial
import time

PORT = "/dev/cu.usbmodem1101"  # CHANGE THIS
BAUD = 9600

ser = serial.Serial(
    PORT,
    BAUD,
    timeout=1
)

time.sleep(2)

print("Connected to Pico")

while True:

    message = input(
        "Enter message (q to quit): "
    )

    if message.lower() == "q":
        break

    ser.write(
        (message + "\n").encode()
    )

    time.sleep(0.1)

    while ser.in_waiting > 0:

        response = (
            ser.readline()
            .decode()
            .strip()
        )

        print("Response:", response)

ser.close()