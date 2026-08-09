import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../../core/app_config.dart';

/// API 호출 실패 시 던지는 예외
class ApiException implements Exception {
  final String message;
  final int? statusCode;
  ApiException(this.message, [this.statusCode]);

  @override
  String toString() => 'ApiException($statusCode): $message';
}

/// 백엔드와 통신하는 공통 HTTP 클라이언트
///
/// ★ 이 클래스가 실제 네트워크 호출을 담당하는 유일한 지점입니다.
/// 각 기능별 Service(CanvasApiService, ImageApiService 등)는
/// 이 클라이언트를 거쳐서만 서버와 통신합니다.
///
/// [AppConfig.useMockApi] 가 true인 동안은 각 기능별 Service에서
/// 이 클래스를 호출하지 않고 자체 mock 데이터를 반환하도록 분기되어 있습니다.
/// (서비스 레이어 코드 참고: canvas_api_service.dart, image_api_service.dart)
class ApiClient {
  ApiClient._();

  static Future<Map<String, dynamic>> post(
    String path,
    Map<String, dynamic> body, {
    String? authToken,
  }) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}$path');
    try {
      final response = await http.post(
        uri,
        headers: {
          'Content-Type': 'application/json',
          if (authToken != null) 'Authorization': 'Bearer $authToken',
        },
        body: jsonEncode(body),
      );

      if (response.statusCode >= 200 && response.statusCode < 300) {
        if (response.body.isEmpty) return {};
        return jsonDecode(response.body) as Map<String, dynamic>;
      }
      throw ApiException('요청이 실패했습니다 (${response.statusCode})', response.statusCode);
    } on ApiException {
      rethrow;
    } catch (e) {
      // 서버가 아직 없거나(Connection refused), 네트워크 문제일 때
      throw ApiException('서버에 연결할 수 없습니다: $e');
    }
  }

  /// multipart/form-data로 파일을 업로드한다 (예: 이미지 모드 `/image/preprocess`).
  static Future<Map<String, dynamic>> postMultipart(
    String path,
    List<int> bytes, {
    required String fieldName,
    required String filename,
    String? contentType,
    String? authToken,
  }) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}$path');
    try {
      final request = http.MultipartRequest('POST', uri)
        ..files.add(http.MultipartFile.fromBytes(
          fieldName,
          bytes,
          filename: filename,
          contentType: contentType != null ? MediaType.parse(contentType) : null,
        ));
      if (authToken != null) {
        request.headers['Authorization'] = 'Bearer $authToken';
      }

      final streamedResponse = await request.send();
      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode >= 200 && response.statusCode < 300) {
        if (response.body.isEmpty) return {};
        return jsonDecode(response.body) as Map<String, dynamic>;
      }
      throw ApiException('요청이 실패했습니다 (${response.statusCode})', response.statusCode);
    } on ApiException {
      rethrow;
    } catch (e) {
      throw ApiException('서버에 연결할 수 없습니다: $e');
    }
  }

  static Future<Map<String, dynamic>> delete(
    String path, {
    String? authToken,
  }) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}$path');
    try {
      final response = await http.delete(
        uri,
        headers: {
          if (authToken != null) 'Authorization': 'Bearer $authToken',
        },
      );

      if (response.statusCode >= 200 && response.statusCode < 300) {
        if (response.body.isEmpty) return {};
        return jsonDecode(response.body) as Map<String, dynamic>;
      }
      throw ApiException('요청이 실패했습니다 (${response.statusCode})', response.statusCode);
    } on ApiException {
      rethrow;
    } catch (e) {
      throw ApiException('서버에 연결할 수 없습니다: $e');
    }
  }

  static Future<Map<String, dynamic>> get(
    String path, {
    Map<String, String>? queryParams,
    String? authToken,
  }) async {
    final uri = Uri.parse('${AppConfig.apiBaseUrl}$path')
        .replace(queryParameters: queryParams);
    try {
      final response = await http.get(
        uri,
        headers: {
          if (authToken != null) 'Authorization': 'Bearer $authToken',
        },
      );

      if (response.statusCode >= 200 && response.statusCode < 300) {
        if (response.body.isEmpty) return {};
        return jsonDecode(response.body) as Map<String, dynamic>;
      }
      throw ApiException('요청이 실패했습니다 (${response.statusCode})', response.statusCode);
    } on ApiException {
      rethrow;
    } catch (e) {
      throw ApiException('서버에 연결할 수 없습니다: $e');
    }
  }
}
