/// Faseeh Share Flet extension.
///
/// Wraps `receive_sharing_intent` and forwards incoming shared files/text to
/// the Python side via a Flet page event named `faseeh_share_receive`:
///   {"files": [{"path": "...", "mime": "...", "text": "...", "source": "share"}]}
library faseeh_share;

import 'dart:async';
import 'package:flet/flet.dart';
import 'package:flutter/material.dart';
import 'package:receive_sharing_intent/receive_sharing_intent.dart';

class FaseehSharePlugin extends UIFletPlugin {
  static FaseehSharePlugin? _instance;
  StreamSubscription? _sub;
  FletControlBackend? _backend;
  String? _pageId;

  factory FaseehSharePlugin() => _instance ??= FaseehSharePlugin._();
  FaseehSharePlugin._();

  @override
  String get type => "faseeh_share";

  @override
  Widget createControl(parent, control, backend) => const SizedBox.shrink();

  @override
  void onMethodCall(method, params, backend) {}

  /// Called once the Flet app control is attached.
  void attach(FletControlBackend backend, String pageId) {
    _backend = backend;
    _pageId = pageId;
    _sub = ReceiveSharingIntent.instance.getMediaStream().listen(_onFiles);
    // Initial media when the app was launched via a share.
    ReceiveSharingIntent.instance.getInitialMedia().then((list) {
      _onFiles(list);
      ReceiveSharingIntent.instance.reset();
    });
  }

  void _onFiles(List<SharedMediaFile> files) {
    if (files.isEmpty || _backend == null || _pageId == null) return;
    final payload = files
        .map((f) => {
              "path": f.path,
              "mime": f.mimeType ?? "",
              "text": f.message ?? "",
              "source": "share",
            })
        .toList();
    _backend!.sendPageEvent(_pageId!, "faseeh_share_receive",
        {"files": payload});
  }

  void dispose() {
    _sub?.cancel();
    _sub = null;
  }
}
