import re
import cv2
import numpy as np
from functools import cached_property


class CharDetection:
    def __init__(self, box, cls, name, conf, parent):
        self.box = box
        self.box_area = box[-1] * box[-2]

        self.w = self.box[2] - self.box[0]
        self.h = self.box[3] - self.box[1]

        self.c = [(self.box[0] + self.box[2]) // 2, (self.box[1] + self.box[3]) // 2]

        self.cls = cls
        self.name = name
        self.conf = conf
        self.parent = parent

        self.wn = self.w / self.parent.w
        self.hn = self.h / self.parent.h

        self.is_touching_edge = False

        self.is_worse_duplicate_of = None
        self.is_better_duplicate_of = None

        self.position_line = None
        self.position_in_line = None

        # small/big
        # for example: in usual plate format serial and region have small chars and number have big chars
        self.relative_size = None
        self.analyzed_name = None
        self.analyzed_size = None

        #  D - digit, c - letter, d - 'D' (in Diplomatic)
        self.type = ('D' if self.name.isdigit() else 'c') if self.name != 'd' else 'd'


class CharDetections:
    GAP_FROM_EDGE_REQUIRED = 0.01

    def __init__(self, result, img):
        self.boxes = result['det'][:, :4]
        self.conf = list(map(float, result['det'][:, 4]))
        self.cls = list(map(int, result['det'][:, 5]))
        self.img = img
        self.h, self.w = self.img.shape[:2]
        self.n = len(self.cls)
        self.names = '0123456789abcdehkmoptxy'
        self.chars: list[CharDetection] = []

        self.double_line = False
        self.analyzed_name = None

        for i in range(self.n):
            char = CharDetection(
                np.array(self.boxes[i], dtype="int32"),
                self.cls[i],
                self.names[self.cls[i]],
                self.conf[i],
                self,
            )
            self.chars.append(char)

        if len(self.chars) >= 6:
            self.find_touching_edge()
            # self.find_duplicates()
            self.order()
            self.analyze()

    def find_touching_edge(self):
        for i in range(self.n):
            touching_top = self.chars[i].box[0] <= self.GAP_FROM_EDGE_REQUIRED*self.w
            touching_bottom = self.chars[i].box[1] >= self.chars[i].parent.h - self.GAP_FROM_EDGE_REQUIRED*self.h
            touching_left = self.chars[i].box[1] <= self.GAP_FROM_EDGE_REQUIRED*self.h
            touching_right = self.chars[i].box[0] >= self.chars[i].parent.w - self.GAP_FROM_EDGE_REQUIRED*self.w
            touching = touching_top or touching_bottom or touching_left or touching_right
            if touching:
                self.chars[i].is_touching_edge = True

    def find_duplicates(self):
        average_height = sum(ch.box[3] - ch.box[1] for ch in self.chars) // len(self.chars)
        for i in range(self.n - 1):
            ch = self.chars[i]
            next_ch = self.chars[i + 1]
            distance = ((next_ch.c[0] - ch.c[0]) ** 2 + (next_ch.c[1] - ch.c[1]) ** 2) ** 0.5
            is_duplicate = distance < average_height // 10
            if is_duplicate:
                if ch.conf >= next_ch.conf:
                    next_ch.is_worse_duplicate_of = ch
                    ch.is_better_duplicate_of = next_ch
                else:
                    next_ch.is_better_duplicate_of = ch
                    ch.is_worse_duplicate_of = next_ch

    def order(self):
        middle = sum(ch.box[1] for ch in self.chars) // len(self.chars)
        average_height = sum(ch.box[3] - ch.box[1] for ch in self.chars) // len(self.chars)
        top = min(ch.box[1] for ch in self.chars)
        bottom = max(ch.box[1] for ch in self.chars)

        lines = []
        if bottom - top > average_height:
            self.double_line = True
            top_line = sorted(
                [ch for ch in self.chars if ch.box[1] < middle],
                key=lambda ch: ch.box[0]
            )
            bottom_line = sorted(
                [ch for ch in self.chars if ch.box[1] >= middle],
                key=lambda ch: ch.box[0]
            )
            lines.append(top_line)
            lines.append(bottom_line)
        else:
            line = sorted(
                self.chars,
                key=lambda ch: ch.box[0]
            )
            lines.append(line)

        j = 0
        for i, line in enumerate(lines):
            for ch in line:
                if ch.is_worse_duplicate_of is not None:
                    continue
                ch.position_line = i
                ch.position_in_line = j
                j += 1

    def analyze(self):
        sorted_by_height = sorted(self.chars, key=lambda ch: ch.hn)
        dif = [sorted_by_height[i+1].hn - sorted_by_height[i].hn for i in range(len(sorted_by_height)-1)]
        gap = max(enumerate(dif), key=lambda x: x[1])
        if gap[1] < 0.07:
            return
        last_small = gap[0]
        for i in range(len(sorted_by_height)):
            if i <= last_small:
                sorted_by_height[i].analyzed_size = 'small'
            else:
                sorted_by_height[i].analyzed_size = 'big'

        processed = self.post_processed
        is_diplomatic = [ch.analyzed_size for ch in processed[:4]] == ['big']*3+['small']
        if not self.double_line and not is_diplomatic:
            # for all chars but not region
            fix_small = {'0': 'o', '9': 'p', '8': 'b', '7': 't'}
            fix_big = {'o': '0', 'p': '9', 'b': '8', 't': '7'}
            for i, ch in enumerate(processed):
                if i < len(processed)-2:
                    if i == len(processed)-3 and ch.name in ('9', '7'):
                        continue
                    if ch.analyzed_size == 'small':
                        if i not in (2, 3):
                            ch.analyzed_name = fix_small.get(ch.name, ch.name)
                    elif ch.analyzed_size == 'big':
                        ch.analyzed_name = fix_big.get(ch.name, ch.name)
                else:
                    if ch.analyzed_size == 'small':
                        ch.analyzed_name = fix_big.get(ch.name, ch.name)
                if ch.analyzed_name != ch.name:
                    # decrease confidence if fixed -> twice farther from 1.0
                    ch.conf = 1 - (1 - ch.conf) * 2

                    # increase confidence if fixed -> twice closer to 1.0
                    ch.conf = 1 - (1 - ch.conf) / 2
        for i, ch in enumerate(processed):
            if ch.analyzed_name is None:
                ch.analyzed_name = ch.name

        if len(processed) < 6:
            return

        if processed[0].analyzed_name.isdigit():
            if processed[3].analyzed_name.isdigit():
                self.analyzed_name = 'military'
            else:
                self.analyzed_name = 'diplomatic'
        elif not processed[1].analyzed_name.isdigit():
            self.analyzed_name = 'public'
        elif processed[4].analyzed_name.isdigit():
            self.analyzed_name = 'police'
        else:
            self.analyzed_name = 'car'


    @property
    def post_processed(self):
        return sorted([
            ch for ch in self.chars
            if (not ch.is_touching_edge) and (ch.is_worse_duplicate_of is None)
        ], key=lambda ch: (ch.position_line, ch.position_in_line))

    @cached_property
    def confs(self):
        return [ch.conf for ch in self.post_processed]

    @cached_property
    def parsed_string(self):
        string = ''.join([ch.analyzed_name or ch.name for ch in self.post_processed]).lower()
        patterns = [
            (r'^([a-ce-z])(\d{3})([a-ce-z]{2})(\d{2,3})$', "car"),  # 'a000aa00'
            (r'^([a-ce-z]{2})(\d{3})(\d{2,3})$', "public"),  # 'aa00000'
            (r'^(\d{4})([a-ce-z]{2})(\d{2,3})$', "military"),  # '0000aa00'
            (r'^(\d{3})(d)(\d{3})(\d{2})$', "diplomatic"),  # '000d00000'
            (r'^([a-ce-z])(\d{4})(\d{2,3})$', "police"),  # 'a000000'
        ]

        for pattern, plate_type in patterns:
            match = re.match(pattern, string)
            if match:
                parts = match.groups()
                return True, plate_type, parts

        return False, None, None

    @cached_property
    def is_valid(self):
        return self.parsed_string[0]

    @cached_property
    def string(self):
        if not self.is_valid:
            return None
        string = ''.join([ch.analyzed_name or ch.name for ch in self.post_processed]).lower()
        return string


class PlatePrediction:
    def __init__(self, box, mask, cls, name, conf, parent):
        self.box = box
        self.box_area = box[-1] * box[-2]
        self.mask = mask.astype(int)

        self.contour = self.mask.reshape(-1, 1, 2)
        epsilon = 0.001 * cv2.arcLength(self.contour, True)
        self.contour = cv2.approxPolyDP(self.contour, epsilon, True)
        self.contour = cv2.convexHull(self.contour)

        self.cls = cls
        self.name = name
        self.conf = conf
        self.parent = parent

    @staticmethod
    def order_points_clockwise(pts):
        x_sorted = pts[np.argsort(pts[:, 0]), :]

        left_most = x_sorted[:2, :]
        right_most = x_sorted[2:, :]

        left_most = left_most[np.argsort(left_most[:, 1]), :]
        (tl, bl) = left_most

        d = np.linalg.norm(tl - right_most, axis=1).argsort()[::-1]
        (br, tr) = right_most[d, :]

        return np.array([tl, tr, br, bl], dtype="float32")

    @staticmethod
    def find_intersection(p1, p2, p3, p4):
        x1, y1 = p1
        x2, y2 = p2
        x3, y3 = p3
        x4, y4 = p4

        a1 = y2 - y1
        b1 = x1 - x2
        c1 = a1 * x1 + b1 * y1

        a2 = y4 - y3
        b2 = x3 - x4
        c2 = a2 * x3 + b2 * y3

        determinant = a1 * b2 - a2 * b1

        if determinant == 0:
            return None

        x = (b2 * c1 - b1 * c2) / determinant
        y = (a1 * c2 - a2 * c1) / determinant

        return [x, y]

    @cached_property
    def corners(self):
        min_area_rect = cv2.minAreaRect(self.contour)
        box = cv2.boxPoints(min_area_rect)
        box = self.order_points_clockwise(box)

        tl = self.find_intersection(*box[:2], [self.box[0], self.box[1]], [self.box[0], self.box[3]])
        tr = self.find_intersection(*box[:2], [self.box[2], self.box[1]], [self.box[2], self.box[3]])
        br = self.find_intersection(*box[2:], [self.box[2], self.box[1]], [self.box[2], self.box[3]])
        bl = self.find_intersection(*box[2:], [self.box[0], self.box[1]], [self.box[0], self.box[3]])

        return np.array([tl, tr, br, bl], dtype="int32")

    @cached_property
    def cropped(self):
        src_pts = np.float32(self.corners)

        w, h = 224, 48
        border_w = 8
        border_h = 4

        too_narrow = (src_pts[1][0] - src_pts[0][0]) / (src_pts[3][1] - src_pts[0][1]) < 1.8
        if self.cls == 1 or too_narrow:
            h *= 2

        dst_pts = np.float32(
            [[border_w, border_h], [w - border_w, border_h], [w - border_w, h - border_h], [border_w, h - border_h]])
        matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        image_transformed = cv2.warpPerspective(self.parent.img, matrix, (w, h))
        return image_transformed


class PlatePredictions:
    def __init__(self, result, img):
        self.boxes = result['det'][:, :4]
        self.masks = result['seg']
        self.names = {i: str(i) for i in range(6)}
        self.cls = list(map(int, result['det'][:, 5]))
        self.conf = list(map(float, result['det'][:, 4]))
        self.img = img
        self.h, self.w = img.shape[:2]
        self.n = len(self.cls)
        self.plates: list[PlatePrediction] = []

        for i in range(self.n):
            plate = PlatePrediction(
                np.array(self.boxes[i], dtype="int32"),
                self.masks[i],
                self.cls[i],
                self.names[self.cls[i]],
                self.conf[i],
                self,
            )
            self.plates.append(plate)

