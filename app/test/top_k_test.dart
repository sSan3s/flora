import 'package:flora/core/model/top_k.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('점수 내림차순으로 k개', () {
    final r = topK([0.1, 0.6, 0.05, 0.25], 3);
    expect(r.map((e) => e.index), [1, 3, 0]);
    expect(r.first.score, 0.6);
  });

  test('k 가 클래스 수보다 크면 전체 반환', () {
    expect(topK([0.3, 0.7], 5).length, 2);
  });
}
