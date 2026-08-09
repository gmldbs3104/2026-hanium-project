"""craft-text-detector==0.4.3의 vgg16_bn.py를 torchvision 0.28+ 호환되게 패치한다.

craft-text-detector 0.4.3은 torchvision에서 이미 제거된
`torchvision.models.vgg.model_urls`를 import하기 때문에, 패치 없이는
`from craft_text_detector import ...` 시점에 ImportError가 난다.
CraftNet은 생성 직후 사전학습 가중치(craft_mlt_25k.pth) 전체로 덮어써지므로
VGG 백본의 ImageNet 사전학습(pretrained=True)은 애초에 불필요하다.

자세한 배경: ai/requirements.txt, ai/BACKEND_INTEGRATION.md §3 "주의 2".

사용법:
    python patch_craft_text_detector.py <venv 경로>
    (예: python patch_craft_text_detector.py backend/venv)

이미 패치된 상태에서 다시 실행해도 안전하다 (idempotent).
"""
import glob
import os
import sys

OLD_IMPORT = "from torchvision.models.vgg import model_urls\n"

OLD_BLOCK = (
    '        model_urls["vgg16_bn"] = model_urls["vgg16_bn"].replace("https://", "http://")\n'
    "        vgg_pretrained_features = models.vgg16_bn(pretrained=pretrained).features"
)
NEW_BLOCK = "        vgg_pretrained_features = models.vgg16_bn(weights=None).features"


def find_target(venv_dir: str) -> str:
    pattern = os.path.join(venv_dir, "**", "craft_text_detector", "models", "basenet", "vgg16_bn.py")
    matches = glob.glob(pattern, recursive=True)
    if not matches:
        raise FileNotFoundError(
            f"vgg16_bn.py를 '{venv_dir}' 안에서 찾지 못했습니다. "
            "먼저 'pip install --no-deps craft-text-detector==0.4.3'을 실행했는지 확인하세요."
        )
    return matches[0]


def patch(path: str) -> None:
    text = open(path, encoding="utf-8").read()

    if OLD_IMPORT not in text and OLD_BLOCK not in text:
        print(f"이미 패치되어 있습니다 (변경 없음): {path}")
        return

    text = text.replace(OLD_IMPORT, "")
    text = text.replace(OLD_BLOCK, NEW_BLOCK)

    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"패치 완료: {path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("사용법: python patch_craft_text_detector.py <venv 경로>")
        sys.exit(1)
    patch(find_target(sys.argv[1]))
