import sys
sys.path.insert(0, ".")
from preprocessing.image_preprocessor import ImagePreprocessor
import cv2

preprocessor = ImagePreprocessor()

for name in ["test_images/test.jpg", "test_images/test2.png",
             "test_images/test3.png", "test_images/test4.png"]:
    r = preprocessor.preprocess_from_file(name)
    h, w = r.binary_image.shape[:2]
    status = "RETAKE" if r.retake_required else "PASS"
    q = r.quality_score["total"]
    print(f"{name}: [{status}]  quality={q}pt  skew={r.skew_angle:+.1f}deg  out={w}x{h}")
    print(f"  filters={r.applied_filters}")

    out = "debug_output/" + name.replace("test_images/", "").replace(".", "_pre.")
    import os; os.makedirs("debug_output", exist_ok=True)
    cv2.imwrite(out, cv2.bitwise_not(r.binary_image))
    print(f"  saved -> {out}")
