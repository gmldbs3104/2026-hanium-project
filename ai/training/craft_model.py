"""
CRAFT 모델 아키텍처 (clovaai/CRAFT-pytorch 기반)
VGG-16 백본 + Double-Conv 업샘플링 + 2채널 출력(region, affinity)
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.models import vgg16_bn


class DoubleConv(nn.Module):
    def __init__(self, in_ch, mid_ch, out_ch):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_ch, mid_ch, 1),
            nn.BatchNorm2d(mid_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(mid_ch, out_ch, 3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.conv(x)


class CRAFT(nn.Module):
    def __init__(self, pretrained_backbone: bool = True, freeze_backbone: bool = False):
        super().__init__()

        # VGG-16 BN 백본 (feature 추출)
        vgg = vgg16_bn(pretrained=pretrained_backbone)
        features = list(vgg.features.children())

        self.slice1 = nn.Sequential(*features[:13])   # conv1~2  → 64ch
        self.slice2 = nn.Sequential(*features[13:20]) # conv3    → 128ch
        self.slice3 = nn.Sequential(*features[20:27]) # conv4    → 256ch
        self.slice4 = nn.Sequential(*features[27:34]) # conv5    → 512ch
        self.slice5 = nn.Sequential(*features[34:],   # conv5 pool → 512ch
                                    nn.MaxPool2d(3, stride=1, padding=1),
                                    nn.Conv2d(512, 1024, 3, padding=6, dilation=6),
                                    nn.Conv2d(1024, 1024, 1))

        if freeze_backbone:
            for p in list(self.slice1.parameters()) + list(self.slice2.parameters()):
                p.requires_grad = False

        # 업샘플링 헤드
        self.up1 = DoubleConv(1024 + 512, 512, 256)
        self.up2 = DoubleConv(256  + 256, 256, 128)
        self.up3 = DoubleConv(128  + 128, 128,  64)
        self.up4 = DoubleConv(64   +  64,  64,  32)

        # 출력: region score + affinity score
        self.out = nn.Sequential(
            nn.Conv2d(32, 32, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(32, 32, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(32,  2, 1),
            nn.Sigmoid(),
        )

    def forward(self, x):
        s1 = self.slice1(x)
        s2 = self.slice2(s1)
        s3 = self.slice3(s2)
        s4 = self.slice4(s3)
        s5 = self.slice5(s4)

        def up(feat, skip):
            feat = F.interpolate(feat, size=skip.shape[2:], mode='bilinear', align_corners=False)
            return torch.cat([feat, skip], dim=1)

        y = self.up1(up(s5, s4))
        y = self.up2(up(y,  s3))
        y = self.up3(up(y,  s2))
        y = self.up4(up(y,  s1))

        out = self.out(y)                        # (B, 2, H/2, W/2)
        return out[:, 0], out[:, 1]              # region, affinity

    def load_pretrained_craft(self, weight_path: str):
        """craft_text_detector 또는 원본 CRAFT 가중치 로드."""
        state = torch.load(weight_path, map_location='cpu')
        # craft_text_detector 형식 대응
        if 'craft' in state:
            state = state['craft']
        # key prefix 제거
        new_state = {}
        for k, v in state.items():
            k = k.replace('module.', '')
            new_state[k] = v
        missing, unexpected = self.load_state_dict(new_state, strict=False)
        print(f"  가중치 로드 완료 | missing={len(missing)} unexpected={len(unexpected)}")
