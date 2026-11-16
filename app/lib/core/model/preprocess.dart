import 'dart:math' as math;
import 'dart:typed_data';

import 'package:image/image.dart' as img;

/// 인코딩된 이미지(jpg/png) → 모델 입력.
/// EXIF 회전을 먼저 적용한다. 폰 사진은 대부분 회전 정보가 따로 붙어 있음.
Float32List preprocess(Uint8List bytes, int size) {
  final decoded = img.decodeImage(bytes);
  if (decoded == null) {
    throw const FormatException('이미지를 디코딩할 수 없음');
  }
  return preprocessImage(img.bakeOrientation(decoded), size);
}

/// ml/common.py 의 eval transform 과 같은 순서.
///   짧은 변을 floor(size * 1.14) 로 리사이즈 → 가운데 size x size 크롭
/// 출력은 NHWC float32, 0~255 RGB. 정규화는 모델 안에서 한다 (export_tflite.py Deploy).
Float32List preprocessImage(img.Image image, int size) {
  final short = (size * 1.14).floor();
  final scale = short / math.min(image.width, image.height);
  final resized = img.copyResize(
    image,
    width: (image.width * scale).round(),
    height: (image.height * scale).round(),
    interpolation: img.Interpolation.linear,
  );
  final cropped = img.copyCrop(
    resized,
    x: (resized.width - size) ~/ 2,
    y: (resized.height - size) ~/ 2,
    width: size,
    height: size,
  );

  final out = Float32List(size * size * 3);
  var i = 0;
  for (var y = 0; y < size; y++) {
    for (var x = 0; x < size; x++) {
      final p = cropped.getPixel(x, y);
      out[i++] = p.rNormalized * 255;
      out[i++] = p.gNormalized * 255;
      out[i++] = p.bNormalized * 255;
    }
  }
  return out;
}
