from enum import Enum

import cv2
import numpy as np
import numpy.typing as npt
from colour import delta_E
from imutils import grab_contours
from imutils.perspective import four_point_transform

from opencv_utils import cvt_single_color


class Color(Enum):
    """Colors."""

    BLUE = 0
    GREEN = 1
    RED = 2
    WHITE = 3
    BLACK = 4


color2bgr = {
    Color.BLUE: (255, 0, 0),
    Color.GREEN: (0, 255, 0),
    Color.RED: (0, 0, 255),
    Color.WHITE: (255, 255, 255),
    Color.BLACK: (0, 0, 0),
}


def find_screen(photo: npt.NDArray, color: Color) -> npt.NDArray:
    """
    Find the screen in the photo.

    :param photo: A photo of the screen.
    :param color: The color of the screen. Cannot be black.
    :return: Four (x, y) points which are the four corners of the screen.
    """
    if color is Color.BLACK:
        raise ValueError("Cannot find a black screen from a photo.")

    # BGR to gray
    if color is Color.WHITE:
        gray = cv2.cvtColor(photo, cv2.COLOR_BGR2GRAY)
    else:
        gray = photo[..., color.value]

    # get the contours
    binary = cv2.threshold(gray, None, 255, cv2.THRESH_OTSU)[1]
    contours = grab_contours(
        cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    )

    # the contour of the screen should be the largest one
    screen_contour = max(contours, key=cv2.contourArea)

    # it should be a quadrilateral
    approx = cv2.approxPolyDP(
        screen_contour, 0.01 * cv2.arcLength(screen_contour, True), True
    )

    # debug
    # noinspection PyUnreachableCode
    if __debug__:
        from opencv_debug import show

        show(photo)
        show(gray)
        show(binary)
        show(photo, contours)
        show(photo, [screen_contour])
        show(photo, [approx])

    if len(approx) != 4:
        raise ValueError("Cannot find the screen.")

    return approx[:, 0, :]


def check_screen(photo: npt.NDArray, color: Color, corners: npt.NDArray) -> float:
    """
    Check if the color of the screen is correct.

    :param photo: A photo of the screen.
    :param color: The color of the screen.
    :param corners: The result of find_screen.
    :return: A float value. Smaller means better.
    """
    # transform to rectangle
    warped = four_point_transform(photo, corners)
    cropped = warped[16:-16, 16:-16]

    # increase the brightness unless the color is black
    bgr = cropped
    if color is not Color.BLACK:
        hsv = cv2.cvtColor(cropped, cv2.COLOR_BGR2HSV)
        hsv[:, :, 2] += 255 - np.max(hsv[:, :, 2])
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    # check the color with delta_E method
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    expected = cvt_single_color(color2bgr[color], cv2.COLOR_BGR2LAB)
    delta_e = delta_E(lab, expected)

    # debug
    # noinspection PyUnreachableCode
    if __debug__:
        from opencv_debug import show

        show(photo)
        show(warped)
        show(cropped)
        show(bgr)
        show(
            255 - cv2.normalize(delta_e.astype(np.uint8), None, 0, 255, cv2.NORM_MINMAX)
        )

    return np.max(delta_e)
