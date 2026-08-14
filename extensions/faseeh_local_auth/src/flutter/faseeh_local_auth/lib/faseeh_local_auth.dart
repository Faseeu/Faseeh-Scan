/// Faseeh Local Auth Flet extension.
///
/// Wraps the `local_auth` plugin and exposes:
///   is_available          -> {available: bool}
///   can_check_biometrics  -> {canCheck: bool}
///   authenticate          -> {authenticated: bool}
library faseeh_local_auth;

import 'package:flet/flet.dart';
import 'package:flutter/material.dart';
import 'package:local_auth/local_auth.dart';

class FaseehLocalAuthPlugin extends UIFletPlugin {
  static FaseehLocalAuthPlugin? _instance;
  final LocalAuthentication _auth = LocalAuthentication();

  factory FaseehLocalAuthPlugin() =>
      _instance ??= FaseehLocalAuthPlugin._();
  FaseehLocalAuthPlugin._();

  @override
  String get type => "faseeh_local_auth";

  @override
  Widget createControl(parent, control, backend) => const SizedBox.shrink();

  @override
  Future<Map<String, dynamic>> handleMethod(
      String method, Map args, BuildContext context) async {
    switch (method) {
      case "is_available":
        try {
          final can = await _auth.isDeviceSupported();
          return {"available": can};
        } catch (_) {
          return {"available": false};
        }
      case "can_check_biometrics":
        try {
          final biometrics = await _auth.getAvailableBiometrics();
          return {"canCheck": biometrics.isNotEmpty};
        } catch (_) {
          return {"canCheck": false};
        }
      case "authenticate":
        try {
          final ok = await _auth.authenticate(
            localizedReason:
                (args["reason"] as String?) ?? "Unlock Faseeh Scan",
            options: const AuthenticationOptions(
              biometricOnly: true,
              stickyAuth: true,
            ),
          );
          return {"authenticated": ok};
        } catch (_) {
          return {"authenticated": false};
        }
      default:
        return {"error": "unknown method"};
    }
  }
}
