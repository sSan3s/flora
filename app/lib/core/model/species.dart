/// classes.json 의 클래스 하나. ml/common.py write_classes_json 과 필드가 1:1.
class Species {
  const Species({
    required this.index,
    required this.key,
    required this.scientific,
    required this.korean,
    required this.taxonomy,
  });

  factory Species.fromJson(Map<String, dynamic> json) => Species(
    index: json['index'] as int,
    key: json['key'] as int,
    scientific: json['scientific'] as String,
    korean: json['korean'] as String,
    taxonomy: (json['taxonomy'] as Map<String, dynamic>).map(
      (rank, name) => MapEntry(rank, name as String?),
    ),
  );

  final int index;
  final int key; // GBIF usageKey
  final String scientific;
  final String korean;
  final Map<String, String?> taxonomy;
}

/// 계 → 종 순서와 한글 표기.
const taxonomyRanks = <(String, String)>[
  ('kingdom', '계'),
  ('phylum', '문'),
  ('class', '강'),
  ('order', '목'),
  ('family', '과'),
  ('genus', '속'),
  ('species', '종'),
];
