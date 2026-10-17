import 'package:flutter/material.dart';

import 'services/app_state.dart';

/// Light palette: warm off-white canvas, white cards, charcoal text, lime accent.
/// Lime is only used as a fill behind charcoal text (it fails contrast as text on
/// white); [AppColors.accentInk] is the accessible green for accent text and icons.
class AppColors {
  static const canvas = Color(0xFFF7F6F2);
  static const surface = Color(0xFFFFFFFF);
  static const surfaceMuted = Color(0xFFEFEEE8);
  static const border = Color(0xFFE2E0D8);
  static const ink = Color(0xFF1C1F23);
  static const inkMuted = Color(0xFF5A5F66);
  static const lime = Color(0xFFC5F036);
  static const limeSoft = Color(0xFFEEFBC4);
  static const accentInk = Color(0xFF3B6300);
  static const cyan = Color(0xFF0E7490);
  static const danger = Color(0xFFB3261E);
}

const _radius = 20.0;

/// Rounded charcoal hero card used for the match score, club and profile headers.
const heroMargin = EdgeInsets.fromLTRB(16, 8, 16, 8);
BoxDecoration heroDecoration() => BoxDecoration(
  // Solid fill: a gradient here rendered transparent on the API 30 emulator,
  // which would leave white text on a pale card.
  color: AppColors.ink,
  borderRadius: BorderRadius.circular(24),
  boxShadow: const [
    BoxShadow(color: Color(0x26000000), blurRadius: 18, offset: Offset(0, 8)),
  ],
);

Color? parseHex(String? hex) {
  if (hex == null) return null;
  var h = hex.trim().replaceFirst('#', '');
  if (h.length == 3) h = h.split('').map((c) => '$c$c').join();
  if (h.length == 6) h = 'FF$h';
  final v = int.tryParse(h, radix: 16);
  return v == null || h.length != 8 ? null : Color(v);
}

/// Tenant branding (logo badge, highlights) stays on the tenant's own colours.
Color tenantPrimary(AppState app) =>
    parseHex(app.tenant?.primaryColor) ?? const Color(0xFF0B3D91);
Color tenantAccent(AppState app) =>
    parseHex(app.tenant?.accentColor) ?? const Color(0xFFF2A900);

ThemeData buildTheme(AppState app) {
  final scheme = ColorScheme.fromSeed(
    seedColor: AppColors.lime,
    brightness: Brightness.light,
  ).copyWith(
    primary: AppColors.accentInk,
    onPrimary: Colors.white,
    primaryContainer: AppColors.lime,
    onPrimaryContainer: AppColors.ink,
    secondary: tenantAccent(app),
    onSecondary:
        ThemeData.estimateBrightnessForColor(tenantAccent(app)) ==
            Brightness.dark
        ? Colors.white
        : AppColors.ink,
    tertiary: tenantPrimary(app),
    onTertiary: Colors.white,
    surface: AppColors.surface,
    onSurface: AppColors.ink,
    onSurfaceVariant: AppColors.inkMuted,
    surfaceContainerLowest: AppColors.surface,
    surfaceContainerLow: AppColors.canvas,
    surfaceContainer: AppColors.surfaceMuted,
    surfaceContainerHigh: AppColors.surfaceMuted,
    surfaceContainerHighest: const Color(0xFFE7E5DE),
    outline: const Color(0xFFB9B6AC),
    outlineVariant: AppColors.border,
    error: AppColors.danger,
  );

  final base = ThemeData(colorScheme: scheme, useMaterial3: true);
  final text = base.textTheme.apply(
    bodyColor: AppColors.ink,
    displayColor: AppColors.ink,
  );
  final shape = RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(_radius),
  );

  return base.copyWith(
    scaffoldBackgroundColor: AppColors.canvas,
    textTheme: text.copyWith(
      headlineSmall: text.headlineSmall?.copyWith(
        fontWeight: FontWeight.w800,
        letterSpacing: -0.4,
      ),
      titleLarge: text.titleLarge?.copyWith(
        fontWeight: FontWeight.w700,
        letterSpacing: -0.2,
      ),
      titleMedium: text.titleMedium?.copyWith(fontWeight: FontWeight.w700),
      labelLarge: text.labelLarge?.copyWith(
        fontWeight: FontWeight.w700,
        letterSpacing: 0.2,
      ),
      bodyMedium: text.bodyMedium?.copyWith(height: 1.4),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: AppColors.canvas,
      foregroundColor: AppColors.ink,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 2,
      shadowColor: Color(0x22000000),
      centerTitle: false,
      titleTextStyle: TextStyle(
        color: AppColors.ink,
        fontSize: 22,
        fontWeight: FontWeight.w800,
        letterSpacing: -0.3,
      ),
    ),
    materialTapTargetSize: MaterialTapTargetSize.padded,
    pageTransitionsTheme: const PageTransitionsTheme(
      builders: {
        TargetPlatform.android: FadeForwardsPageTransitionsBuilder(),
      },
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: AppColors.lime,
        foregroundColor: AppColors.ink,
        disabledBackgroundColor: AppColors.surfaceMuted,
        disabledForegroundColor: AppColors.inkMuted,
        minimumSize: const Size(64, 52),
        elevation: 0,
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AppColors.ink,
        minimumSize: const Size(64, 48),
        side: const BorderSide(color: Color(0xFFCFCCC2)),
        shape: const StadiumBorder(),
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: AppColors.accentInk,
        minimumSize: const Size(48, 48),
        textStyle: const TextStyle(fontWeight: FontWeight.w700),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: AppColors.surface,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: AppColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: AppColors.accentInk, width: 2),
      ),
    ),
    cardTheme: CardThemeData(
      color: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 1.5,
      shadowColor: const Color(0x1F000000),
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
      shape: shape.copyWith(side: const BorderSide(color: AppColors.border)),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      indicatorColor: AppColors.lime,
      elevation: 3,
      shadowColor: const Color(0x22000000),
      height: 72,
      labelTextStyle: WidgetStateProperty.resolveWith(
        (s) => TextStyle(
          fontSize: 12.5,
          color: AppColors.ink,
          fontWeight: s.contains(WidgetState.selected)
              ? FontWeight.w800
              : FontWeight.w500,
        ),
      ),
      iconTheme: WidgetStateProperty.resolveWith(
        (s) => IconThemeData(
          color: s.contains(WidgetState.selected)
              ? AppColors.ink
              : AppColors.inkMuted,
        ),
      ),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: SegmentedButton.styleFrom(
        selectedBackgroundColor: AppColors.limeSoft,
        selectedForegroundColor: AppColors.ink,
        foregroundColor: AppColors.ink,
        side: const BorderSide(color: AppColors.border),
        minimumSize: const Size(48, 48),
      ),
    ),
    chipTheme: base.chipTheme.copyWith(
      backgroundColor: AppColors.surfaceMuted,
      side: BorderSide.none,
      shape: const StadiumBorder(),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      shape: shape,
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: AppColors.surface,
      surfaceTintColor: Colors.transparent,
      showDragHandle: true,
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: AppColors.ink,
      contentTextStyle: const TextStyle(color: Colors.white, fontSize: 15),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
    ),
    dividerTheme: const DividerThemeData(color: AppColors.border, space: 1),
    listTileTheme: const ListTileThemeData(
      minVerticalPadding: 10,
      iconColor: AppColors.inkMuted,
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: AppColors.accentInk,
    ),
  );
}
