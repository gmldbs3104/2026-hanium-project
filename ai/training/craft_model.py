"""
CRAFT 모델 아키텍처 — clovaai/CRAFT-pytorch(craft_text_detector 패키지) 공식 구조를 그대로 vendor.

ai/detection/craft_detector.py가 추론에 쓰는 craft_text_detector.models.craftnet.CraftNet과
state_dict 키가 100% 동일하도록 구성한다 (basenet.slice1~5, upconv1~4.conv.*, conv_cls.*).
학습 결과 체크포인트를 craft_text_detector.Craft(weight_path_craft_net=...)에 바로 로드하기
위한 것이므로, 아래 서브모듈 이름/중첩 구조를 임의로 바꾸지 말 것.

craft_text_detector 패키지를 import하지 않고 직접 복제한 이유: 이 파일은 Google Colab처럼
그 패키지가 설치되어 있지 않거나(또는 최신 torchvision/numpy와 버전이 안 맞아 패치가 필요한)
환경에서도 실행돼야 하므로, torch/torchvision 표준 API에만 의존하게 만들기 위함.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision import models


def _init_weights(modules):
    for m in modules:
        if isinstance(m, nn.Conv2d):
            nn.init.xavier_uniform_(m.weight.data)
            if m.bias is not None:
                m.bias.data.zero_()
        elif isinstance(m, nn.BatchNorm2d):
            m.weight.data.fill_(1)
            m.bias.data.zero_()


class _VGG16BNBase(nn.Module):
    """VGG16-BN backbone. clovaai CRAFT의 slice1~5 경계(12/19/29/39) 그대로."""

    def __init__(self, pretrained: bool = True, freeze: bool = True):
        super().__init__()
        weights = models.VGG16_BN_Weights.IMAGENET1K_V1 if pretrained else None
        features = models.vgg16_bn(weights=weights).features

        # 주의: nn.Sequential(*list)는 자식을 "0","1",..로 재번호해버려 공식 state_dict와
        # 키가 어긋난다. 공식 구현처럼 add_module(str(원래 인덱스), ...)로 원래 VGG feature
        # 인덱스를 서브모듈 이름으로 그대로 보존해야 한다.
        self.slice1 = nn.Sequential()
        self.slice2 = nn.Sequential()
        self.slice3 = nn.Sequential()
        self.slice4 = nn.Sequential()
        for x in range(0, 12):    # conv2_2  → 128ch
            self.slice1.add_module(str(x), features[x])
        for x in range(12, 19):   # conv3_3  → 256ch
            self.slice2.add_module(str(x), features[x])
        for x in range(19, 29):   # conv4_3  → 512ch
            self.slice3.add_module(str(x), features[x])
        for x in range(29, 39):   # conv5_3  → 512ch
            self.slice4.add_module(str(x), features[x])
        self.slice5 = nn.Sequential(                                        # fc6/fc7  → 1024ch
            nn.MaxPool2d(kernel_size=3, stride=1, padding=1),
            nn.Conv2d(512, 1024, kernel_size=3, padding=6, dilation=6),
            nn.Conv2d(1024, 1024, kernel_size=1),
        )

        if not pretrained:
            _init_weights(self.slice1.modules())
            _init_weights(self.slice2.modules())
            _init_weights(self.slice3.modules())
            _init_weights(self.slice4.modules())
        _init_weights(self.slice5.modules())   # fc6/fc7는 항상 새로 초기화 (pretrained 없음)

        if freeze:
            for p in self.slice1.parameters():
                p.requires_grad = False

    def forward(self, x):
        h = self.slice1(x); relu2_2 = h
        h = self.slice2(h); relu3_2 = h
        h = self.slice3(h); relu4_3 = h
        h = self.slice4(h); relu5_3 = h
        h = self.slice5(h); fc7 = h
        return fc7, relu5_3, relu4_3, relu3_2, relu2_2


class _DoubleConv(nn.Module):
    """clovaai double_conv: 첫 conv 입력 채널 = in_ch(concat 전) + mid_ch(skip)."""

    def __init__(self, in_ch, mid_ch, out_ch):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch + mid_ch, mid_ch, kernel_size=1),
            nn.BatchNorm2d(mid_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(mid_ch, out_ch, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.conv(x)


class CRAFT(nn.Module):
    """
    clovaai/CRAFT-pytorch 공식 구조와 state_dict 키가 100% 동일한 학습용 CRAFT.
    forward()는 sigmoid 없는 raw score(공식 구조 그대로)를 (region, affinity)로 반환한다 —
    학습 loss(CRAFTLoss)에서 0~1 Gaussian GT와 MSE로 직접 비교하는 것이 표준 방식.
    """

    def __init__(self, pretrained_backbone: bool = True, freeze_backbone: bool = False):
        super().__init__()
        self.basenet = _VGG16BNBase(pretrained=pretrained_backbone, freeze=freeze_backbone)

        self.upconv1 = _DoubleConv(1024, 512, 256)
        self.upconv2 = _DoubleConv(512, 256, 128)
        self.upconv3 = _DoubleConv(256, 128, 64)
        self.upconv4 = _DoubleConv(128, 64, 32)

        num_class = 2
        self.conv_cls = nn.Sequential(
            nn.Conv2d(32, 32, kernel_size=3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(32, 32, kernel_size=3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(32, 16, kernel_size=3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(16, 16, kernel_size=1), nn.ReLU(inplace=True),
            nn.Conv2d(16, num_class, kernel_size=1),
        )
        _init_weights(self.upconv1.modules())
        _init_weights(self.upconv2.modules())
        _init_weights(self.upconv3.modules())
        _init_weights(self.upconv4.modules())
        _init_weights(self.conv_cls.modules())

    def forward(self, x):
        fc7, relu5_3, relu4_3, relu3_2, relu2_2 = self.basenet(x)

        y = torch.cat([fc7, relu5_3], dim=1)
        y = self.upconv1(y)

        y = F.interpolate(y, size=relu4_3.shape[2:], mode='bilinear', align_corners=False)
        y = torch.cat([y, relu4_3], dim=1)
        y = self.upconv2(y)

        y = F.interpolate(y, size=relu3_2.shape[2:], mode='bilinear', align_corners=False)
        y = torch.cat([y, relu3_2], dim=1)
        y = self.upconv3(y)

        y = F.interpolate(y, size=relu2_2.shape[2:], mode='bilinear', align_corners=False)
        y = torch.cat([y, relu2_2], dim=1)
        feature = self.upconv4(y)

        out = self.conv_cls(feature)             # (B, 2, H/2, W/2) — sigmoid 없음
        return out[:, 0], out[:, 1]               # region, affinity

    def load_pretrained_craft(self, weight_path: str):
        """craft_mlt_25k.pth 등 공식 CRAFT 가중치 로드 (키 이름이 동일하므로 대부분 그대로 매칭)."""
        state = torch.load(weight_path, map_location='cpu')
        if 'craft' in state:
            state = state['craft']
        new_state = {k.replace('module.', ''): v for k, v in state.items()}
        missing, unexpected = self.load_state_dict(new_state, strict=False)
        print(f"  가중치 로드 완료 | missing={len(missing)} unexpected={len(unexpected)}")
