import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';

import '../models/models.dart';
import '../services/api_client.dart';
import '../services/app_state.dart';
import '../services/sync_service.dart';
import '../widgets/common.dart';

class PaymentOption {
  final String token;
  final String title;
  final String subtitle;
  const PaymentOption(this.token, this.title, this.subtitle);
}

const paymentOptions = [
  PaymentOption(
    'tok_success',
    'Test card: approved',
    'Payment goes through (tok_success)',
  ),
  PaymentOption(
    'tok_declined',
    'Test card: declined',
    'Bank declines the payment (tok_declined)',
  ),
  PaymentOption(
    'tok_capture_fail',
    'Test card: capture fails',
    'Approved, then capture fails (tok_capture_fail)',
  ),
];

class CartScreen extends StatefulWidget {
  const CartScreen({super.key});

  @override
  State<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends State<CartScreen> {
  final _discount = TextEditingController();
  String _token = 'tok_success';
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _discount.dispose();
    super.dispose();
  }

  Future<void> _checkout() async {
    final app = AppScope.read(context);
    if (!app.connectivity.isOnline) {
      final reachable = await app.connectivity.check();
      if (!reachable) {
        if (mounted) {
          showError(
            context,
            'You are offline. Checkout needs an internet connection.',
          );
        }
        return;
      }
    }
    if (!mounted) return;
    final option = paymentOptions.firstWhere((o) => o.token == _token);
    final ok = await confirm(
      context,
      title: 'Confirm purchase',
      message:
          'Pay ${formatMoney(app.cartTotal)} for ${app.cartCount} item(s) using "${option.title}"?'
          '${_discount.text.trim().isNotEmpty ? '\nDiscount code: ${_discount.text.trim().toUpperCase()}' : ''}',
      confirmLabel: 'Pay now',
    );
    if (!ok || !mounted) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final code = _discount.text.trim();
      final names = {
        for (final l in app.cart)
          l.variant.variantId: '${l.product.name} (${l.variant.label})',
      };
      final result = await app.repo.checkout({
        'order_id': randomId('ord'),
        'customer_id': app.user?.playerId ?? app.user?.email ?? 'customer',
        'items': app.cart
            .map(
              (l) => {
                'variant_id': l.variant.variantId,
                'quantity': l.quantity,
              },
            )
            .toList(),
        'discount_code': code.isEmpty ? null : code.toUpperCase(),
        'payment': {'token': _token},
      });
      if (!mounted) return;
      app.clearCart();
      showSuccess(
        context,
        'Payment successful! Order ${result.orderId} is paid.',
      );
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => ReceiptScreen(result: result, names: names),
        ),
      );
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    return Scaffold(
      appBar: const LeagueAppBar(title: 'Your cart'),
      body: app.cart.isEmpty
          ? MessageView(
              icon: Icons.shopping_cart_outlined,
              title: 'Your cart is empty',
              message: 'Browse the store and add something you like.',
              actionLabel: 'Back to store',
              onAction: () => Navigator.of(context).pop(),
            )
          : SafeArea(
              child: ListView(
                padding: const EdgeInsets.all(12),
                children: [
                  for (final l in app.cart)
                    Card(
                      margin: const EdgeInsets.symmetric(vertical: 6),
                      child: Padding(
                        padding: const EdgeInsets.all(8),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    l.product.name,
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                  Text(
                                    '${l.variant.label} · ${formatMoney(l.variant.priceMinor)} each',
                                  ),
                                  Text(
                                    formatMoney(l.totalMinor),
                                    style: const TextStyle(
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            IconButton(
                              tooltip: l.quantity == 1
                                  ? 'Remove ${l.product.name}'
                                  : 'Decrease quantity',
                              onPressed: () =>
                                  app.setQuantity(l, l.quantity - 1),
                              icon: Icon(
                                l.quantity == 1
                                    ? Icons.delete_outline
                                    : Icons.remove,
                              ),
                            ),
                            Text(
                              '${l.quantity}',
                              style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            IconButton(
                              tooltip: 'Increase quantity',
                              onPressed:
                                  l.quantity < 10 &&
                                      l.quantity < l.variant.stock
                                  ? () => app.setQuantity(l, l.quantity + 1)
                                  : null,
                              icon: const Icon(Icons.add),
                            ),
                          ],
                        ),
                      ),
                    ),
                  const SizedBox(height: 8),
                  TextField(
                    controller: _discount,
                    textCapitalization: TextCapitalization.characters,
                    decoration: const InputDecoration(
                      labelText: 'Discount code (optional)',
                      hintText: 'e.g. WELCOME10',
                      prefixIcon: Icon(Icons.discount_outlined),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Payment method (test gateway)',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  RadioGroup<String>(
                    groupValue: _token,
                    onChanged: (v) => setState(() => _token = v ?? _token),
                    child: Column(
                      children: [
                        for (final o in paymentOptions)
                          RadioListTile<String>(
                            value: o.token,
                            title: Text(o.title),
                            subtitle: Text(o.subtitle),
                          ),
                      ],
                    ),
                  ),
                  const Divider(),
                  Row(
                    children: [
                      const Text('Total', style: TextStyle(fontSize: 18)),
                      const Spacer(),
                      Text(
                        formatMoney(app.cartTotal),
                        style: TextStyle(
                          fontSize: 22,
                          fontWeight: FontWeight.w800,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                      ),
                    ],
                  ),
                  const Text(
                    'Discounts are applied by the server at checkout.',
                    style: TextStyle(fontSize: 12),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: const Color(0xFFFFEBEE),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Row(
                        children: [
                          const Icon(
                            Icons.error_outline,
                            color: Color(0xFFB71C1C),
                            semanticLabel: 'Error',
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              _error!,
                              style: const TextStyle(color: Color(0xFFB71C1C)),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                  const SizedBox(height: 16),
                  FilledButton.icon(
                    key: const Key('pay'),
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(56),
                    ),
                    onPressed: _busy ? null : _checkout,
                    icon: _busy
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.lock),
                    label: Text(
                      _busy
                          ? 'Processing payment...'
                          : 'Pay ${formatMoney(app.cartTotal)}',
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}

class ReceiptScreen extends StatefulWidget {
  final CheckoutResult result;
  final Map<String, String> names;
  const ReceiptScreen({super.key, required this.result, this.names = const {}});

  @override
  State<ReceiptScreen> createState() => _ReceiptScreenState();
}

class _ReceiptScreenState extends State<ReceiptScreen> {
  String? _savedPath;
  bool _busy = false;

  Future<File> _save() async {
    final r = widget.result;
    final bytes = base64Decode(r.pdfBase64!.replaceAll(RegExp(r'\s'), ''));
    Directory dir;
    try {
      dir =
          (await getExternalStorageDirectory()) ??
          await getApplicationDocumentsDirectory();
    } catch (_) {
      dir = await getApplicationDocumentsDirectory();
    }
    final safe = r.orderId.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '_');
    final file = File('${dir.path}/receipt-$safe.pdf');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<void> _saveAndOpen({bool open = true}) async {
    setState(() => _busy = true);
    try {
      final f = await _save();
      if (!mounted) return;
      setState(() => _savedPath = f.path);
      if (open) {
        final res = await OpenFilex.open(f.path, type: 'application/pdf');
        if (!mounted) return;
        if (res.type != ResultType.done) {
          showInfo(
            context,
            'Receipt saved to ${f.path}. No PDF viewer app was found to open it.',
          );
          return;
        }
      }
      showSuccess(context, 'Receipt saved to ${f.path}');
    } catch (_) {
      if (mounted) {
        showError(context, 'The receipt could not be saved on this phone.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final r = widget.result;
    final hasPdf = r.pdfBase64 != null && r.pdfBase64!.isNotEmpty;
    return Scaffold(
      appBar: const LeagueAppBar(title: 'Receipt'),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Icon(
              Icons.check_circle,
              color: Color(0xFF2E7D32),
              size: 64,
              semanticLabel: 'Payment successful',
            ),
            const SizedBox(height: 8),
            Text(
              'Payment successful',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 4),
            Text('Order ${r.orderId}', textAlign: TextAlign.center),
            if (r.paidAt != null)
              Text(
                'Paid ${friendlyTime(r.paidAt)}',
                textAlign: TextAlign.center,
              ),
            const SizedBox(height: 16),
            Card(
              margin: EdgeInsets.zero,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  children: [
                    for (final it in r.items)
                      _line(
                        '${widget.names[it['variant_id']] ?? it['variant_id']} x ${it['quantity']}',
                        formatMoney(
                          ((it['unit_price_minor'] ?? 0) as num).toInt() *
                              ((it['quantity'] ?? 1) as num).toInt(),
                          r.currency,
                        ),
                      ),
                    const Divider(),
                    _line('Subtotal', formatMoney(r.subtotalMinor, r.currency)),
                    _line(
                      'Discount',
                      '- ${formatMoney(r.discountMinor, r.currency)}',
                    ),
                    _line(
                      'Total paid',
                      formatMoney(r.totalMinor, r.currency),
                      bold: true,
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            if (hasPdf) ...[
              FilledButton.icon(
                key: const Key('open_receipt'),
                onPressed: _busy ? null : () => _saveAndOpen(),
                icon: const Icon(Icons.picture_as_pdf),
                label: const Text('Open PDF receipt'),
              ),
              const SizedBox(height: 8),
              OutlinedButton.icon(
                onPressed: _busy ? null : () => _saveAndOpen(open: false),
                icon: const Icon(Icons.download),
                label: const Text('Save PDF to phone'),
              ),
              if (_savedPath != null) ...[
                const SizedBox(height: 8),
                Text(
                  'Saved at: $_savedPath',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ] else
              const Text(
                'The PDF receipt is not available for this order.',
                textAlign: TextAlign.center,
              ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Back to store'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _line(String a, String b, {bool bold = false}) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(
      children: [
        Expanded(
          child: Text(
            a,
            style: TextStyle(fontWeight: bold ? FontWeight.bold : null),
          ),
        ),
        Text(
          b,
          style: TextStyle(
            fontWeight: bold ? FontWeight.bold : null,
            fontSize: bold ? 18 : null,
          ),
        ),
      ],
    ),
  );
}
