from enum import Enum
from typing import Literal

import cv2
import numpy as np
import numpy.typing as npt
from PIL import Image
from colour import delta_E
from imutils import grab_contours
from imutils.perspective import four_point_transform
from pytesseract import image_to_string

from opencv_utils import cvt_single_color

debug = False


class Color(Enum):
    """Colors."""

    BLUE = 0
    GREEN = 1
    RED = 2
    WHITE = 3
    BLACK = 4


_color2bgr = {
    Color.BLUE: (1, 0, 0),
    Color.GREEN: (0, 1, 0),
    Color.RED: (0, 0, 1),
    Color.WHITE: (1, 1, 1),
    Color.BLACK: (0, 0, 0),
}


def find_screen(photo: npt.NDArray, color: Color, strict: bool = False) -> npt.NDArray:
    """
    Find the screen in the photo.

    :param photo: A photo of the screen.
    :param color: The color of the screen. Cannot be black.
    :param strict: Raise an error if multiple contours are found.
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
    contours = tuple(filter(lambda c: cv2.contourArea(c) > 4, contours))

    # strict mode
    if strict and len(contours) > 1:
        raise ValueError("Multiple contours found.")

    # the contour of the screen should be the largest one
    screen_contour = max(contours, key=cv2.contourArea)

    # it should be a quadrilateral
    approx = cv2.approxPolyDP(
        screen_contour, 0.01 * cv2.arcLength(screen_contour, True), True
    )

    if debug:
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


def get_lengths(corners: npt.NDArray) -> tuple[float, ...]:
    """
    Get the lengths of the four sides of the screen.

    :param corners: The result of find_screen.
    :return: A tuple of four float values.
    """
    return tuple(np.linalg.norm(corners[i] - corners[(i + 1) % 4]) for i in range(4))


def get_size(corner: npt.NDArray) -> float:
    """
    Get the size of the screen.

    :param corner: The result of find_screen.
    :return: The size of the screen.
    """
    # See https://stackoverflow.com/a/30408825/13805358.
    x, y = corner[:, 0], corner[:, 1]
    return 0.5 * np.abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def check_screen(
    photo: npt.NDArray,
    color: Color,
    corners: npt.NDArray,
    method: Literal[
        "CIE 1976",
        "CIE 1994",
        "CIE 2000",
        "CMC",
        "CAM02-LCD",
        "CAM02-SCD",
        "CAM02-UCS",
        "CAM16-LCD",
        "CAM16-SCD",
        "CAM16-UCS",
        "DIN99",
    ] = "CIE 2000",
) -> float:
    """
    Check if the color of the screen is correct.

    :param photo: A photo of the screen.
    :param color: The color of the screen.
    :param corners: The result of find_screen.
    :param method: The computation method of delta_E.
    :return: A float value between 0 and 100. Smaller means better.
    """
    # transform to rectangle
    warped = four_point_transform(photo, corners)
    cropped = warped[16:-16, 16:-16]

    # check the color with delta_E method
    lab = cv2.cvtColor(cropped.astype(np.float32) / 255, cv2.COLOR_BGR2LAB)
    expected = cvt_single_color(_color2bgr[color], cv2.COLOR_BGR2LAB, np.float32)
    delta_e = delta_E(lab, expected, method=method)

    if debug:
        from opencv_debug import show

        show(photo)
        show(warped)
        show(cropped)

        normalized = cv2.normalize(delta_e, None, 0, 255, cv2.NORM_MINMAX)
        equalized = cv2.equalizeHist(normalized.astype(np.uint8))
        inverted = cv2.bitwise_not(equalized)
        show(inverted)

    return np.max(delta_e)


def ocr_ssd(photo: npt.NDArray) -> str:
    """
    Optical character recognition for seven-segment display.

    :param photo: A photo of the screen with some seven-segment display text.
    :return: The text on the screen.
    """
    # get the screen
    corners = find_screen(photo, Color.WHITE)
    warped = four_point_transform(photo, corners)

    # The following steps are not necessary for getting the correct result.
    # But doing so improves the performance.

    # convert to binary
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, None, 255, cv2.THRESH_OTSU)[1]

    # crop to the text
    x, y, w, h = cv2.boundingRect(binary)
    cropped = binary[y : y + h, x : x + w]

    # add borders
    # see https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html#missing-borders
    border_width = 10
    bordered = cv2.copyMakeBorder(
        cropped,
        top=border_width,
        bottom=border_width,
        left=border_width,
        right=border_width,
        borderType=cv2.BORDER_CONSTANT,
        value=(0, 0, 0),
    )

    if debug:
        from opencv_debug import show

        show(warped)
        show(gray)
        show(binary)
        show(cropped)
        show(bordered)

    return image_to_string(Image.fromarray(bordered), "lets", "--psm 8").strip()
