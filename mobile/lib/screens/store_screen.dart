import 'package:flutter/material.dart';

import '../models/models.dart';
import '../services/app_state.dart';
import '../widgets/common.dart';
import '../widgets/loader.dart';
import 'checkout_screen.dart';

class CartButton extends StatelessWidget {
  const CartButton({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final n = app.cartCount;
    return IconButton(
      tooltip: n == 0 ? 'Cart is empty' : 'Cart, $n items',
      onPressed: () =>
          Navigator.of(context)
              .push(MaterialPageRoute(builder: (_) => const CartScreen())),
      icon: Badge(
        isLabelVisible: n > 0,
        label: Text('$n'),
        child: const Icon(Icons.shopping_cart),
      ),
    );
  }
}

class StoreScreen extends StatelessWidget {
  const StoreScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.read(context);
    return Scaffold(
      appBar: const LeagueAppBar(title: 'Store', actions: [CartButton()]),
      body: Loader<List<Product>>(
        loadingMessage: 'Loading store...',
        load: () => app.repo.products(),
        builder: (context, products, refresh) => RefreshIndicator(
          onRefresh: refresh,
          child: products.isEmpty
              ? ListView(
                  children: const [
                    SizedBox(
                      height: 360,
                      child: EmptyView(
                        icon: Icons.storefront,
                        title: 'No products yet',
                        message: 'Club merchandise will appear here.',
                      ),
                    ),
                  ],
                )
              : ListView.builder(
                  padding: const EdgeInsets.only(bottom: 16),
                  itemCount: products.length,
                  itemBuilder: (context, i) =>
                      ProductCard(product: products[i]),
                ),
        ),
      ),
    );
  }
}

class ProductCard extends StatelessWidget {
  final Product product;
  const ProductCard({super.key, required this.product});

  @override
  Widget build(BuildContext context) {
    final p = product;
    final price = p.minPrice;
    final inStock = p.variants.any((v) => v.stock > 0);
    return Card(
      child: InkWell(
        onTap: () => Navigator.of(context)
            .push(MaterialPageRoute(builder: (_) => ProductScreen(product: p))),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              CircleAvatar(
                radius: 26,
                backgroundColor: Theme.of(context)
                    .colorScheme
                    .secondaryContainer,
                child: Icon(
                  _iconFor(p.category),
                  semanticLabel: p.category.isEmpty ? 'Product' : p.category,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      p.name,
                      style: const TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    if (p.category.isNotEmpty)
                      Text(
                        p.category,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    const SizedBox(height: 4),
                    Text(
                      inStock ? 'In stock' : 'Out of stock',
                      style: TextStyle(
                        color: inStock
                            ? const Color(0xFF1B5E20)
                            : const Color(0xFFB71C1C),
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Text(
                price == null ? '' : formatMoney(price),
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

IconData _iconFor(String category) {
  final c = category.toLowerCase();
  if (c.contains('jersey') || c.contains('shirt') || c.contains('apparel')) {
    return Icons.checkroom;
  }
  if (c.contains('ticket')) return Icons.confirmation_number;
  if (c.contains('ball') || c.contains('equipment')) return Icons.sports_soccer;
  return Icons.shopping_bag;
}

class ProductScreen extends StatefulWidget {
  final Product product;
  const ProductScreen({super.key, required this.product});

  @override
  State<ProductScreen> createState() => _ProductScreenState();
}

class _ProductScreenState extends State<ProductScreen> {
  Variant? _variant;
  int _qty = 1;

  @override
  void initState() {
    super.initState();
    final vs = widget.product.variants;
    _variant = vs.where((v) => v.stock > 0).firstOrNull ?? vs.firstOrNull;
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.product;
    final v = _variant;
    final maxQty = v == null ? 1 : v.stock.clamp(1, 10);
    return Scaffold(
      appBar: LeagueAppBar(title: p.name, actions: const [CartButton()]),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Center(
              child: CircleAvatar(
                radius: 48,
                backgroundColor: Theme.of(context)
                    .colorScheme
                    .secondaryContainer,
                child: Icon(
                  _iconFor(p.category),
                  size: 48,
                  semanticLabel: p.category,
                ),
              ),
            ),
            const SizedBox(height: 12),
            Text(p.name, style: Theme.of(context).textTheme.headlineSmall),
            if (p.description.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(p.description),
            ],
            const SizedBox(height: 16),
            Text(
              'Choose an option',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            if (p.variants.isEmpty)
              const Text('This product has no options available.'),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final x in p.variants)
                  ChoiceChip(
                    label: Text(
                      x.stock > 0 ? x.label : '${x.label} (sold out)',
                    ),
                    selected: _variant?.variantId == x.variantId,
                    onSelected: x.stock > 0
                        ? (_) => setState(() {
                            _variant = x;
                            _qty = 1;
                          })
                        : null,
                  ),
              ],
            ),
            if (v != null) ...[
              const SizedBox(height: 16),
              Text(
                formatMoney(v.priceMinor, v.currency),
                style: TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.w800,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
              Text(v.stock > 0 ? '${v.stock} left in stock' : 'Sold out'),
              const SizedBox(height: 12),
              Row(
                children: [
                  const Text('Quantity', style: TextStyle(fontSize: 16)),
                  const Spacer(),
                  IconButton.outlined(
                    tooltip: 'Decrease quantity',
                    onPressed: _qty > 1 ? () => setState(() => _qty--) : null,
                    icon: const Icon(Icons.remove),
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: Text(
                      '$_qty',
                      style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  IconButton.outlined(
                    tooltip: 'Increase quantity',
                    onPressed: _qty < maxQty
                        ? () => setState(() => _qty++)
                        : null,
                    icon: const Icon(Icons.add),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 20),
            FilledButton.icon(
              key: const Key('add_to_cart'),
              onPressed: (v == null || v.stock <= 0)
                  ? null
                  : () {
                      AppScope.read(context).addToCart(p, v, _qty);
                      ScaffoldMessenger.of(context)
                        ..hideCurrentSnackBar()
                        ..showSnackBar(
                          SnackBar(
                            backgroundColor: const Color(0xFF2E7D32),
                            content: Text(
                              'Added $_qty x ${p.name} (${v.label}) to your cart.',
                            ),
                            action: SnackBarAction(
                              label: 'View cart',
                              textColor: Colors.white,
                              onPressed: () => Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) => const CartScreen(),
                                ),
                              ),
                            ),
                          ),
                        );
                    },
              icon: const Icon(Icons.add_shopping_cart),
              label: const Text('Add to cart'),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: (v == null || v.stock <= 0)
                  ? null
                  : () {
                      AppScope.read(context).addToCart(p, v, _qty);
                      Navigator.of(context).push(
                        MaterialPageRoute(builder: (_) => const CartScreen()),
                      );
                    },
              icon: const Icon(Icons.flash_on),
              label: const Text('Buy now'),
            ),
          ],
        ),
      ),
    );
  }
}
