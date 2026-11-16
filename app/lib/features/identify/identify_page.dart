import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../../core/model/classifier.dart';
import '../../core/model/species.dart';

/// v0 식별 화면. 촬영/갤러리 → 추론 → 후보 3개 + 1순위 분류 계층.
/// 커스텀 카메라 화면(와이어프레임 1번)은 camera 패키지로 다음 단계에서 교체.
class IdentifyPage extends StatefulWidget {
  const IdentifyPage({super.key});

  @override
  State<IdentifyPage> createState() => _IdentifyPageState();
}

class _IdentifyPageState extends State<IdentifyPage> {
  static const _lowConfidence = 0.5;

  final _picker = ImagePicker();
  Classifier? _classifier;
  String? _error;
  Uint8List? _image;
  List<Prediction>? _results;
  int? _elapsedMs;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    Classifier.load()
        .then((c) {
          if (mounted) setState(() => _classifier = c);
        })
        .catchError((Object e) {
          if (mounted) {
            setState(
              () => _error =
                  '모델을 불러오지 못함. 저장소 루트에서 '
                  'tool/fetch_models.sh 로 모델을 받은 뒤 다시 실행하세요.\n\n$e',
            );
          }
        });
  }

  @override
  void dispose() {
    _classifier?.close();
    super.dispose();
  }

  Future<void> _pick(ImageSource source) async {
    final classifier = _classifier;
    if (classifier == null || _busy) return;

    final XFile? file;
    try {
      // 원본 12MP 를 그대로 디코딩하면 수 초 걸림. 피커 단계에서 1024px 로 줄임
      file = await _picker.pickImage(
        source: source,
        maxWidth: 1024,
        maxHeight: 1024,
        imageQuality: 92,
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('사진을 가져오지 못함: $e')));
      return;
    }
    if (file == null) return;

    final bytes = await file.readAsBytes();
    setState(() {
      _busy = true;
      _image = bytes;
      _results = null;
    });

    final sw = Stopwatch()..start();
    try {
      final results = await classifier.classify(bytes);
      if (!mounted) return;
      setState(() {
        _results = results;
        _elapsedMs = sw.elapsedMilliseconds;
      });
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text('식별 실패: $e')));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('꽃 식별')),
      body: SafeArea(child: _body(context)),
      bottomNavigationBar: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
          child: Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: _classifier == null || _busy
                      ? null
                      : () => _pick(ImageSource.camera),
                  icon: const Icon(Icons.photo_camera_outlined),
                  label: const Text('촬영'),
                  style: FilledButton.styleFrom(
                    minimumSize: const Size.fromHeight(52),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: _classifier == null || _busy
                      ? null
                      : () => _pick(ImageSource.gallery),
                  icon: const Icon(Icons.photo_library_outlined),
                  label: const Text('갤러리'),
                  style: OutlinedButton.styleFrom(
                    minimumSize: const Size.fromHeight(52),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _body(BuildContext context) {
    if (_error != null) {
      return Padding(padding: const EdgeInsets.all(20), child: Text(_error!));
    }
    if (_classifier == null) {
      return const Center(child: CircularProgressIndicator());
    }

    final theme = Theme.of(context);
    final results = _results;

    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
      children: [
        AspectRatio(
          aspectRatio: 1,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(14),
            child: _image == null
                ? ColoredBox(
                    color: theme.colorScheme.surfaceContainerHighest,
                    child: Center(
                      child: Text(
                        '꽃을 찍거나 갤러리에서 고르세요',
                        style: theme.textTheme.bodyMedium,
                      ),
                    ),
                  )
                : Image.memory(_image!, fit: BoxFit.cover),
          ),
        ),
        const SizedBox(height: 16),
        if (_busy) const LinearProgressIndicator(),
        if (results != null) ...[
          if (results.first.score < _lowConfidence)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(
                '확신이 낮음. 꽃이 화면 가운데에 크게 오도록 다시 찍어보세요.',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.error,
                ),
              ),
            ),
          for (final p in results) _PredictionTile(prediction: p),
          const SizedBox(height: 16),
          _TaxonomyRail(species: results.first.species),
          const SizedBox(height: 12),
          Text(
            '추론 $_elapsedMs ms · 모델 ${_classifier!.species.length}종',
            style: theme.textTheme.bodySmall,
          ),
        ],
      ],
    );
  }
}

class _PredictionTile extends StatelessWidget {
  const _PredictionTile({required this.prediction});
  final Prediction prediction;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final s = prediction.species;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(s.korean, style: theme.textTheme.titleMedium),
                Text(
                  s.scientific,
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ],
            ),
          ),
          SizedBox(
            width: 72,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text('${(prediction.score * 100).toStringAsFixed(0)}%'),
                const SizedBox(height: 4),
                LinearProgressIndicator(value: prediction.score),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TaxonomyRail extends StatelessWidget {
  const _TaxonomyRail({required this.species});
  final Species species;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('분류', style: theme.textTheme.labelLarge),
        const SizedBox(height: 6),
        for (final (rank, label) in taxonomyRanks)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(
              children: [
                SizedBox(
                  width: 24,
                  child: Text(label, style: theme.textTheme.bodySmall),
                ),
                Text(
                  species.taxonomy[rank] ?? '-',
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}
