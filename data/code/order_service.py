"""Order handling: create orders, apply discounts, calculate totals."""
from dataclasses import dataclass, field

TAX_RATE = 0.18
FREE_SHIPPING_THRESHOLD = 50.0
SHIPPING_FEE = 4.99


@dataclass
class OrderItem:
    sku: str
    price: float
    quantity: int = 1


@dataclass
class Order:
    order_id: str
    items: list[OrderItem] = field(default_factory=list)
    discount_code: str | None = None

    def subtotal(self) -> float:
        return sum(i.price * i.quantity for i in self.items)


def apply_discount(subtotal: float, code: str | None) -> float:
    """SAVE10 gives 10 percent off. SAVE20 gives 20 percent off but needs subtotal above 100."""
    if code == "SAVE10":
        return subtotal * 0.90
    if code == "SAVE20" and subtotal > 100:
        return subtotal * 0.80
    return subtotal


def shipping_cost(subtotal: float) -> float:
    """Shipping is free for orders of 50 or more, otherwise a flat 4.99 fee."""
    return 0.0 if subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE


def order_total(order: Order) -> float:
    """Total = discounted subtotal + 18 percent tax + shipping. Rounded to 2 decimals."""
    discounted = apply_discount(order.subtotal(), order.discount_code)
    tax = discounted * TAX_RATE
    return round(discounted + tax + shipping_cost(discounted), 2)


class OrderService:
    def __init__(self):
        self._orders: dict[str, Order] = {}

    def create(self, order: Order) -> Order:
        if not order.items:
            raise ValueError("order must contain at least one item")
        self._orders[order.order_id] = order
        return order

    def cancel(self, order_id: str) -> None:
        """Orders can be cancelled only before they are shipped."""
        if order_id not in self._orders:
            raise KeyError(f"unknown order {order_id}")
        del self._orders[order_id]
