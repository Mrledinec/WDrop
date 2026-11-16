import 'package:material_ui/material_ui.dart';

import 'screens/home_screen.dart';

void main() => runApp(const LocalTransferApp());

class LocalTransferApp extends StatelessWidget {
  const LocalTransferApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Обмен файлами',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(colorSchemeSeed: const Color(0xff2458a5)),
    darkTheme: ThemeData(
      colorSchemeSeed: const Color(0xff6ea6ff),
      brightness: Brightness.dark,
    ),
    home: const HomeScreen(),
  );
}
