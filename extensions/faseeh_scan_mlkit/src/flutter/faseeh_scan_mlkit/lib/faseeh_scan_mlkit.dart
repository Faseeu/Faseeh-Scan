/// Faseeh Scan ML Kit extension for Flet.
///
/// Wraps google_mlkit_document_scanner and exposes two methods to Python:
///   - is_available
///   - scan  (with page_limit; returns {pdf_path, image_paths})
library faseeh_scan_mlkit;

import 'dart:io';

import 'package:flet/flet.dart';
import 'package:flutter/material.dart';
import 'package:google_mlkit_document_scanner/google_mlkit_document_scanner.dart';

class FaseehScanMlkitException implements Exception {
  final String message;
  FaseehScanMlkitException(this.message);
  @override
  String toString() => "FaseehScanMlkitException: $message";
}

class FaseehScanMlkit extends StatelessWidget {
  final Control? parent;
  final Control control;
  final FletControlBackend backend;

  const FaseehScanMlkit({
    super.key,
    required this.parent,
    required this.control,
    required this.backend,
  });

  @override
  Widget build(BuildContext context) {
    return const SizedBox.shrink();
  }
}

class FaseehScanMlkitPlugin extends UIFletPlugin {
  static FaseehScanMlkitPlugin? _instance;
  final Map<String, void Function(Map<String, dynamic>)> _pending = {};

  factory FaseehScanMlkitPlugin() => _instance ??= FaseehScanMlkitPlugin._();
  FaseehScanMlkitPlugin._();

  @override
  String get type => "faseeh_scan_mlkit";

  @override
  Widget createControl(
      Control parent, Control control, FletControlBackend backend) {
    return FaseehScanMlkit(
      parent: parent,
      control: control,
      backend: backend,
    );
  }

  @override
  void onMethodCall(
      String method, Map<String, String> params, FletControlBackend backend) {}

  /// Called from Python via page.invoke_method on the extension.
  Future<Map<String, dynamic>> handleMethod(
      String method, Map args, BuildContext context) async {
    switch (method) {
      case "is_available":
        return {"available": Platform.isAndroid};
      case "scan":
        return await _scan(args);
      default:
        throw FaseehScanMlkitException("Unknown method: $method");
    }
  }

  Future<Map<String, dynamic>> _scan(Map args) async {
    final int pageLimit = (args["page_limit"] ?? 0) as int;
    final options = DocumentScannerOptions(
      documentFormat: DocumentFormat.pdf,
      mode: ScannerMode.filter,
      pageLimit: pageLimit,
      isGalleryImport: true,
    );
    final scanner = DocumentScanner(options: options);
    try {
      final result = await scanner.scanDocument();
      final imagePaths = <String>[];
      for (final p in (result.scannedImages ?? [])) {
        final path = await _copyToAppCache(p);
        if (path != null) imagePaths.add(path);
      }
      return {
        "pdf_path": result.pdf?.uri?.toString() ?? "",
        "image_paths": imagePaths,
      };
    } finally {
      scanner.close();
    }
  }

  /// The scanner returns content Uris; copy to a cache file Python can read.
  Future<String?> _copyToAppCache(Uri uri) async {
    try {
      // For content:// uris we rely on the returned path; ML Kit plugin gives
      // a file path in scannedImages. Best-effort.
      return uri.toFilePath();
    } catch (_) {
      return uri.toString();
    }
  }
}
