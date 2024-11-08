import cv2
import numpy as np
import torch
from openvino import InferRequest
from predictors import ops


def letterbox_image(
        image: np.ndarray,
        target_size: tuple[int, int],
        stride: int = 32,
) -> np.ndarray:
    ih, iw = image.shape[:2]
    tw, th = target_size

    scale = min(tw/iw, th/ih)
    nw, nh = int(scale * iw), int(scale * ih)

    new_image = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)

    vertical = (th - nh) % stride
    horizontal = (tw - nw) % stride

    top = (th - nh) % stride // 2
    left = (tw - nw) % stride // 2
    bottom = vertical - top
    right = horizontal - left

    new_image = cv2.copyMakeBorder(
        new_image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114)
    )

    return new_image


def image_to_tensor(image: np.ndarray):
    input_tensor = image.transpose((2, 0, 1))
    input_tensor = np.ascontiguousarray(input_tensor)
    input_tensor = input_tensor.astype(np.float32)
    input_tensor = input_tensor / 255.0
    input_tensor = np.expand_dims(input_tensor, 0)
    return input_tensor


def clip_coords(coords, shape):
    if isinstance(coords, torch.Tensor):  # faster individually (WARNING: inplace .clamp_() Apple MPS bug)
        coords[..., 0] = coords[..., 0].clamp(0, shape[1])  # x
        coords[..., 1] = coords[..., 1].clamp(0, shape[0])  # y
    else:  # np.array (faster grouped)
        coords[..., 0] = coords[..., 0].clip(0, shape[1])  # x
        coords[..., 1] = coords[..., 1].clip(0, shape[0])  # y
    return coords


def postprocess(request: InferRequest, original_shape, number_classes: int):
    input_hw = request.get_input_tensor(0).data.shape[2:]

    pred_boxes = request.get_output_tensor(0).data
    pred_masks = request.get_output_tensor(1).data if len(request.outputs) > 1 else None

    # only first from the batch
    pred = ops.non_max_suppression(
        torch.from_numpy(pred_boxes),
        nc=number_classes,
        iou_thres=0.2
    )[0]
    proto = torch.from_numpy(pred_masks)[0] if pred_masks is not None else None

    detections = np.array([])
    segments = np.array([]) if pred_masks is not None else None

    if len(pred) == 0:
        return detections, segments

    if proto is not None:
        masks = ops.process_mask_native(proto, pred[:, 6:], pred[:, :4], input_hw)
        segments = [
            ops.scale_coords(input_hw, x, original_shape, normalize=False) for x in ops.masks2segments(masks)
        ]

    pred[:, :4] = ops.scale_boxes(input_hw, pred[:, :4], original_shape).round()
    detections = pred[:, :6].numpy()

    return detections, segments
