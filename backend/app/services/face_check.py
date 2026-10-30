"""人脸检测：判断一张图要不要先入火山素材库。

为什么需要这一步：
    火山 Seedance 不收**直接上传**的真人脸参考图 —— 提交即 400
    `InputImageSensitiveContentDetected.PrivacyInformation`。
    先把图传进素材库拿 `asset://` 再提交，就不会逐次做人脸拦截。

判据只要「有没有脸」，不需要认出是谁 —— 所以用 OpenCV 自带的 YuNet（200KB），
不上大模型、不联网、不吃 GPU。检测不出（模型缺失/图片读不了）时返回 -1，
调用方按「可能需要入库」处理：**宁多入库，不漏一张**（漏一张就是一次 400）。
"""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

_detector = None
_model_loaded_for = ""


def _get_detector():
    """YuNet 检测器（进程内复用）。模型缺文件就返回 None。"""
    global _detector, _model_loaded_for
    from app.core.config import settings

    path = str(settings.face_model or "")
    if _detector is not None and _model_loaded_for == path:
        return _detector
    if not path or not Path(path).exists():
        log.warning("人脸模型不存在（%s），入库判断按「有脸」处理", path)
        _detector, _model_loaded_for = None, path
        return None
    try:
        import cv2

        _detector = cv2.FaceDetectorYN_create(path, "", (320, 320),
                                             score_threshold=0.6)
        _model_loaded_for = path
        return _detector
    except Exception as e:  # noqa: BLE001
        log.warning("人脸模型加载失败：%s", e)
        _detector, _model_loaded_for = None, path
        return None


def detect_faces(src: Path | str) -> int:
    """返回检出的人脸数；-1 = 判断不了（调用方按「有脸」处理）。"""
    import cv2

    det = _get_detector()
    if det is None:
        return -1
    try:
        img = cv2.imread(str(src))
        if img is None:
            return -1
        h, w = img.shape[:2]
        # 大图先缩到长边 1024：YuNet 本来就是小模型，4K 原图只是白算
        if max(w, h) > 1024:
            scale = 1024.0 / max(w, h)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
            h, w = img.shape[:2]
        det.setInputSize((w, h))
        _, faces = det.detect(img)
        return 0 if faces is None else len(faces)
    except Exception as e:  # noqa: BLE001
        log.warning("人脸检测失败 %s：%s", src, e)
        return -1


def has_face(src: Path | str) -> bool:
    """要不要把它当"含真人脸"处理（判断不了也算有）。"""
    return detect_faces(src) != 0
