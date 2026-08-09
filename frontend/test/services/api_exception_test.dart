import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:frontend/shared/services/api_client.dart';

http.Response _response(int statusCode, String body) => http.Response(
      body,
      statusCode,
      headers: {'content-type': 'application/json'},
    );

void main() {
  group('ApiException.fromResponse', () {
    test('detail이 문자열이면 serverMessage로 그대로 쓴다', () {
      final e = ApiException.fromResponse(
        _response(400, '{"detail": "JPG, PNG, WEBP 형식만 지원합니다."}'),
      );

      expect(e.serverMessage, 'JPG, PNG, WEBP 형식만 지원합니다.');
      expect(e.statusCode, 400);
    });

    test('detail이 validation error 배열이면 msg들을 join한다', () {
      final e = ApiException.fromResponse(
        _response(422,
            '{"detail": [{"msg": "field required", "loc": ["body", "width"]}, {"msg": "value error"}]}'),
      );

      expect(e.serverMessage, 'field required, value error');
    });

    test('body가 JSON이 아니면 serverMessage는 null이고 기존 문구로 폴백한다', () {
      final e = ApiException.fromResponse(_response(500, 'Internal Server Error'));

      expect(e.serverMessage, isNull);
      expect(e.message, '요청이 실패했습니다 (500)');
    });

    test('detail 필드가 없으면 serverMessage는 null이다', () {
      final e = ApiException.fromResponse(_response(404, '{"other": "x"}'));

      expect(e.serverMessage, isNull);
    });
  });
}
