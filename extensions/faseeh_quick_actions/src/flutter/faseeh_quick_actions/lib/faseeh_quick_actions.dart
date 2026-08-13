/// Faseeh Quick Actions Flet extension.
///
/// Registers a long-press app-icon shortcut "Scan document" and forwards
/// the shortcut launch to Python as a `faseeh_shortcut` page event:
///   {"action": "scan"}
library faseeh_quick_actions;

import 'package:flet/flet.dart';
import 'package:flutter/material.dart';
import 'package:quick_actions/quick_actions.dart';

class FaseehQuickActionsPlugin extends UIFletPlugin {
  static FaseehQuickActionsPlugin? _instance;
  FletControlBackend? _backend;
  String? _pageId;
  final QuickActions _quickActions = const QuickActions();

  factory FaseehQuickActionsPlugin() =>
      _instance ??= FaseehQuickActionsPlugin._();
  FaseehQuickActionsPlugin._();

  @override
  String get type => "faseeh_quick_actions";

  @override
  Widget createControl(parent, control, backend) => const SizedBox.shrink();

  @override
  void onMethodCall(method, params, backend) {}

  void attach(FletControlBackend backend, String pageId) {
    _backend = backend;
    _pageId = pageId;
    _quickActions.initialize((shortcutType) {
      if (shortcutType == 'scan') {
        _backend?.sendPageEvent(_pageId!, "faseeh_shortcut", {"action": "scan"});
      }
    });
    _quickActions.setShortcutItems(<ShortcutItem>[
      const ShortcutItem(
        type: 'scan',
        localizedTitle: 'Scan document',
        icon: 'ic_scan',
      ),
    ]);
  }
}
