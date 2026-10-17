import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'screens/home_shell.dart';
import 'screens/login_screen.dart';
import 'services/app_state.dart';
import 'services/local_store.dart';
import 'services/token_store.dart';
import 'widgets/common.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final state = AppState(
    client: http.Client(),
    tokens: SecureTokenStore(),
    store: SqliteLocalStore(),
  );
  state.init();
  runApp(LeagueApp(state: state));
}

Color? parseHex(String? hex) {
  if (hex == null) return null;
  var h = hex.trim().replaceFirst('#', '');
  if (h.length == 3) h = h.split('').map((c) => '$c$c').join();
  if (h.length == 6) h = 'FF$h';
  final v = int.tryParse(h, radix: 16);
  return v == null || h.length != 8 ? null : Color(v);
}

ThemeData buildTheme(AppState app) {
  final primary = parseHex(app.tenant?.primaryColor) ?? const Color(0xFF0B3D91);
  final accent = parseHex(app.tenant?.accentColor) ?? const Color(0xFFF2A900);
  final scheme = ColorScheme.fromSeed(seedColor: primary).copyWith(
    primary: primary,
    onPrimary: ThemeData.estimateBrightnessForColor(primary) == Brightness.dark
        ? Colors.white
        : Colors.black,
    secondary: accent,
    onSecondary: ThemeData.estimateBrightnessForColor(accent) == Brightness.dark
        ? Colors.white
        : Colors.black,
  );
  return ThemeData(
    colorScheme: scheme,
    useMaterial3: true,
    appBarTheme: AppBarTheme(
      backgroundColor: scheme.primary,
      foregroundColor: scheme.onPrimary,
    ),
    materialTapTargetSize: MaterialTapTargetSize.padded,
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(64, 48),
        textStyle: const TextStyle(fontSize: 16),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(minimumSize: const Size(64, 48)),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(minimumSize: const Size(48, 48)),
    ),
    inputDecorationTheme: const InputDecorationTheme(
      border: OutlineInputBorder(),
    ),
    cardTheme: const CardThemeData(
      margin: EdgeInsets.symmetric(horizontal: 12, vertical: 6),
    ),
    listTileTheme: const ListTileThemeData(minVerticalPadding: 10),
  );
}

class LeagueApp extends StatelessWidget {
  final AppState state;
  const LeagueApp({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    return AppScope(
      state: state,
      child: ListenableBuilder(
        listenable: state,
        builder: (context, _) => MaterialApp(
          title: 'NaSCon League',
          debugShowCheckedModeBanner: false,
          theme: buildTheme(state),
          home: !state.ready
              ? const Scaffold(body: LoadingView(message: 'Starting...'))
              : state.loggedIn
              ? HomeShell(key: ValueKey(state.user!.email))
              : const LoginScreen(),
        ),
      ),
    );
  }
}
