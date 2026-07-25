// 이 파일은 image_download.dart의 조건부 import로 "웹에서만" 로드된다.
// 따라서 dart:html 사용은 의도된 것이며, 아래 두 lint는 이 파일에 한해 억제한다.
// ignore_for_file: deprecated_member_use, avoid_web_libraries_in_flutter
import 'dart:html' as html;
import 'dart:typed_data';

/// 웹: PNG 바이트를 Blob으로 만들어 브라우저 다운로드를 트리거한다.
Future<void> downloadPng(Uint8List bytes, String filename) async {
  final blob = html.Blob(<Uint8List>[bytes], 'image/png');
  final url = html.Url.createObjectUrlFromBlob(blob);
  final anchor = html.AnchorElement(href: url)
    ..download = filename
    ..style.display = 'none';
  html.document.body?.append(anchor);
  anchor.click();
  anchor.remove();
  html.Url.revokeObjectUrl(url);
}
