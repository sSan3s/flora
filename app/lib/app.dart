import 'package:flutter/material.dart';

import 'features/identify/identify_page.dart';

/// 와이어프레임 강조색. 하이파이 단계에서 ThemeData 를 따로 정리할 예정.
const floraGreen = Color(0xFF3A7F4B);

class FloraApp extends StatelessWidget {
  const FloraApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Flora',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: floraGreen, useMaterial3: true),
      home: const IdentifyPage(),
    );
  }
}
