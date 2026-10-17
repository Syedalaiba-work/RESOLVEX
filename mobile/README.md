# NaSCon League – Android app (Flutter)

The Android client for the RESOLVEX backend. It uses the `/api/v1/*` routes described in `docs/MOBILE_API.md`.

## Install
A prebuilt APK is at `mobile/release/app-release.apk`. It needs Android 7.0 (API 24) or newer, so Android 10+ works.

```
adb install -r mobile/release/app-release.apk
```

## Build
Flutter 3.47 / Dart 3.13 and the Android SDK are required.

```
cd mobile
flutter pub get
flutter analyze
flutter test
flutter build apk --release
cp build/app/outputs/flutter-apk/app-release.apk release/app-release.apk
```

## Server address
The default is `http://10.0.2.2:8080`, which is the host machine as seen from the Android emulator.
On a real phone, open **Settings** (the gear icon on the sign-in screen, or Profile → Server settings).
Enter `http://<laptop LAN IP>:8080` and tap **Save and test connection**. The address is saved on the phone.
The phone and the laptop must be on the same Wi-Fi. Cleartext HTTP is enabled for this.

## Demo accounts (password `Nascon@26`)
| Role | Email | Extra tab |
|---|---|---|
| Super-Admin | admin@nascon.test | Manage (scoring, roster, clubs, sync) |
| League Organizer | organizer@nascon.test | Scoring |
| Club Manager | manager@nascon.test | Roster |
| Player | player@nascon.test | – |
| Viewer | viewer@nascon.test | – |

The sign-in screen has a chip for each demo account that fills in the email and password.

## Features
- Bottom navigation: Fixtures, Standings, Store, Profile, plus one tab for the role.
- Theme colours and the logo badge come from the tenant branding returned at login.
- The match screen updates the live score every 3 s while it is visible. It also shows the event timeline and the pinned product.
- Store: catalogue → variant picker → cart → checkout with a test card (`tok_success`, `tok_declined`, `tok_capture_fail`) → receipt. The receipt can save or open the PDF.
- The session token and user snapshot are kept in `flutter_secure_storage`, which uses the Android Keystore.

## Offline
- The app checks for the server with `GET /api/v1/ping` every 5 s. The chip in the app bar shows Online, Offline or Syncing; tap it to open the sync queue.
- Fixtures, leagues, standings, clubs, club profiles, matches, products and rosters are cached in SQLite (`sqflite`). Cached data appears when offline, under an "Offline: showing saved data" banner.
- Score events, corrections and roster moves made offline go into a SQLite queue that survives a force-close. Each action uses the exact spec 5.14 format: `action_id`, `type`, `queued_at`, `base_version`, `payload`.
- When the server is reachable again, the queue syncs on its own through `POST /api/v1/sync`. There is also a **Sync now** button on the Sync status screen.
- After a sync, each action shows Applied, Already applied or Rejected, with a plain-language reason.

## Code layout
`lib/models` (data classes) · `lib/services` (API client, secure token store, SQLite store, connectivity, sync queue, repository) · `lib/screens` · `lib/widgets`.
Tests (`test/`) use a fake backend built on `package:http/testing.dart` and in-memory stores.
