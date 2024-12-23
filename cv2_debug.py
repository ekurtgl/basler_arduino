import cv2
import numpy as np

frame = np.zeros((500, 500, 3), dtype=np.uint8)  # Black frame
cv2.imshow('Test Window', frame)
cv2.waitKey(0)  # Press any key to close
cv2.destroyAllWindows()
