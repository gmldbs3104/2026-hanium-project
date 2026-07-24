/// SFR-003I Inputs: 선택적 관심영역(ROI) 좌표.
///
/// 원본 촬영 이미지의 픽셀 좌표계를 기준으로 한 사각형 영역이다.
/// 백엔드 `/api/v1/image/preprocess` 요청 바디의 `roi` 필드로 전송된다.
///
/// ⚠️ 백엔드 계약 미확정: 좌표 단위(픽셀 vs 정규화)와 필드명은 협의 필요.
///    현재는 원본 픽셀 좌표(정수)로 보낸다.
class ImageRoi {
  final int x;
  final int y;
  final int width;
  final int height;

  const ImageRoi({
    required this.x,
    required this.y,
    required this.width,
    required this.height,
  });

  Map<String, dynamic> toJson() => {
        'x': x,
        'y': y,
        'width': width,
        'height': height,
      };
}
