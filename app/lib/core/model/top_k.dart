class Ranked {
  const Ranked(this.index, this.score);
  final int index;
  final double score;
}

/// 점수 내림차순 상위 k 개.
List<Ranked> topK(List<double> scores, int k) {
  final ranked = [for (var i = 0; i < scores.length; i++) Ranked(i, scores[i])]
    ..sort((a, b) => b.score.compareTo(a.score));
  return ranked.take(k).toList();
}
