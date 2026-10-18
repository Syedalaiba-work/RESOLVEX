import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'screens/deep_link_screen.dart';
import 'screens/home_shell.dart';
import 'screens/login_screen.dart';
import 'services/app_state.dart';
import 'services/local_store.dart';
import 'services/token_store.dart';
import 'theme.dart';
import 'widgets/common.dart';

export 'theme.dart' show buildTheme, parseHex;

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
          // nascon:// links arrive as the initial route (Part II §6.3).
          onGenerateRoute: deepLinkRoute,
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
