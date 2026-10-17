import 'package:flutter/material.dart';

import '../services/app_state.dart';
import '../widgets/common.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _url;
  bool _testing = false;

  @override
  void initState() {
    super.initState();
    _url = TextEditingController(text: AppScope.read(context).serverUrl);
  }

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    final app = AppScope.read(context);
    setState(() => _testing = true);
    await app.setServerUrl(_url.text);
    _url.text = app.serverUrl;
    final ok = await app.connectivity.check();
    if (!mounted) return;
    setState(() => _testing = false);
    if (ok) {
      showSuccess(context, 'Saved. The server is reachable.');
    } else {
      showError(
        context,
        'Saved, but the server cannot be reached at ${app.serverUrl}. '
        'Check that the laptop and phone are on the same Wi-Fi.',
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: const LeagueAppBar(title: 'Server settings'),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text(
              'Server address',
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
            ),
            const SizedBox(height: 8),
            TextField(
              key: const Key('server_url'),
              controller: _url,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(
                labelText: 'Server address',
                hintText: 'http://192.168.1.10:8080',
                prefixIcon: Icon(Icons.dns_outlined),
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Android emulator: http://10.0.2.2:8080\n'
              'Real phone: http://<laptop Wi-Fi IP>:8080 (same network as the laptop)',
            ),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _testing ? null : _save,
              icon: _testing
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.save),
              label: const Text('Save and test connection'),
            ),
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: () => _url.text = kDefaultServer,
              child: const Text('Use emulator default'),
            ),
          ],
        ),
      ),
    );
  }
}
