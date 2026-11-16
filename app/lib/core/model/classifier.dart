import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:tflite_flutter/tflite_flutter.dart';

import 'preprocess.dart';
import 'species.dart';
import 'top_k.dart';

class Prediction {
  const Prediction(this.species, this.score);
  final Species species;
  final double score;
}

/// flower_cls.tflite 래퍼.
/// 전처리는 compute 로, 추론은 IsolateInterpreter 로 각각 별도 isolate 에서 돌려
/// UI 스레드가 멈추지 않게 한다.
class Classifier {
  Classifier._(this._interpreter, this._runner, this.species, this.inputSize);

  static const modelAsset = 'assets/models/flower_cls.tflite';
  static const classesAsset = 'assets/models/classes.json';

  final Interpreter _interpreter;
  final IsolateInterpreter _runner;
  final List<Species> species;
  final int inputSize;

  static Future<Classifier> load() async {
    final meta = jsonDecode(
      await rootBundle.loadString(classesAsset),
    ) as Map<String, dynamic>;
    final input = meta['input'] as Map<String, dynamic>;
    final species = [
      for (final c in meta['classes'] as List)
        Species.fromJson(c as Map<String, dynamic>),
    ];
    final interpreter = await Interpreter.fromAsset(modelAsset);
    final runner = await IsolateInterpreter.create(
      address: interpreter.address,
    );
    return Classifier._(interpreter, runner, species, input['size'] as int);
  }

  Future<List<Prediction>> classify(Uint8List imageBytes, {int k = 3}) async {
    final pixels = await compute(_preprocessEntry, (imageBytes, inputSize));
    final output = [List<double>.filled(species.length, 0)];
    // Float32List 의 바이트를 그대로 입력 텐서 [1, S, S, 3] 에 복사
    await _runner.run(pixels.buffer.asUint8List(), output);
    return [
      for (final r in topK(output.first, k))
        Prediction(species[r.index], r.score),
    ];
  }

  Future<void> close() async {
    await _runner.close();
    _interpreter.close();
  }
}

// compute 는 최상위 함수만 받는다. 메서드 안 클로저를 넘기면 this 까지 isolate 로 보내려다 실패함.
Float32List _preprocessEntry((Uint8List, int) args) =>
    preprocess(args.$1, args.$2);
