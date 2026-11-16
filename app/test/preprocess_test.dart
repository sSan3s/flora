import 'package:flora/core/model/preprocess.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;

void main() {
  test('출력 길이 size*size*3, RGB 순서와 0~255 범위 유지', () {
    final image = img.Image(width: 640, height: 480);
    img.fill(image, color: img.ColorRgb8(10, 200, 30));

    final out = preprocessImage(image, 224);

    expect(out.length, 224 * 224 * 3);
    expect(out[0], closeTo(10, 1));
    expect(out[1], closeTo(200, 1));
    expect(out[2], closeTo(30, 1));
    expect(out.every((v) => v >= 0 && v <= 255), isTrue);
  });

  test('가로로 긴 사진은 가운데를 자른다 (eval transform 과 동일)', () {
    // 빨강 | 초록 | 파랑 3등분 → 가운데 크롭의 중심은 초록이어야 함
    final image = img.Image(width: 600, height: 300);
    img.fillRect(
      image,
      x1: 0,
      y1: 0,
      x2: 199,
      y2: 299,
      color: img.ColorRgb8(255, 0, 0),
    );
    img.fillRect(
      image,
      x1: 200,
      y1: 0,
      x2: 399,
      y2: 299,
      color: img.ColorRgb8(0, 255, 0),
    );
    img.fillRect(
      image,
      x1: 400,
      y1: 0,
      x2: 599,
      y2: 299,
      color: img.ColorRgb8(0, 0, 255),
    );

    final out = preprocessImage(image, 224);
    const center = (112 * 224 + 112) * 3;

    expect(out[center], closeTo(0, 1));
    expect(out[center + 1], closeTo(255, 1));
    expect(out[center + 2], closeTo(0, 1));
  });

  test('인코딩된 바이트 입력 처리', () {
    final image = img.Image(width: 300, height: 300);
    img.fill(image, color: img.ColorRgb8(100, 100, 100));

    expect(preprocess(img.encodePng(image), 224).length, 224 * 224 * 3);
  });
}
