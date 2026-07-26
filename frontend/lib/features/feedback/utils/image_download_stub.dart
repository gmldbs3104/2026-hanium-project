import 'dart:typed_data';

/// 웹이 아닌 플랫폼용 기본 구현.
/// (android/ios에서의 갤러리/파일 저장은 별도 플러그인+권한이 필요하므로 추후 구현)
Future<void> downloadPng(Uint8List bytes, String filename) async {
  throw UnsupportedError('현재 플랫폼에서는 이미지 다운로드를 지원하지 않습니다.');
}
