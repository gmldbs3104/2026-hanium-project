import 'dart:typed_data';

// 플랫폼별 구현을 조건부 import로 선택한다.
//  - 웹(dart.library.html 사용 가능): 브라우저 Blob 다운로드
//  - 그 외(모바일 등): 미지원(호출 측에서 예외를 잡아 안내)
import 'image_download_stub.dart'
    if (dart.library.html) 'image_download_web.dart' as impl;

/// PNG 바이트를 사용자 기기에 다운로드한다.
Future<void> downloadPng(Uint8List bytes, String filename) =>
    impl.downloadPng(bytes, filename);
