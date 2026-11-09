import cv2

camera = cv2.VideoCapture(0)

if not camera.isOpened():
    print("Cannot open Arducam")
    exit()

while True:
    success, frame = camera.read()

    if not success:
        print("Cannot read camera")
        break

    cv2.imshow("Arducam Test", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

camera.release()
cv2.destroyAllWindows()