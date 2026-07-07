import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user, require_permission
from app.models.shop import Product, ShopOrder, CartItem

router = APIRouter(prefix="/shop", tags=["shop"])


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    image: Optional[str] = None
    icon: Optional[str] = "star"
    category: Optional[str] = "Boshqa"
    # Accept both 'price' (frontend alias) and 'coins' (native)
    price: Optional[int] = None
    coins: Optional[int] = None
    price_sum: Optional[int] = None
    stock: Optional[int] = None   # frontend alias for quantity
    quantity: Optional[int] = None
    is_active: bool = True

    def effective_coins(self) -> int:
        return self.price or self.coins or 0

    def effective_quantity(self) -> int:
        return self.stock or self.quantity or 10


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    icon: Optional[str] = None
    category: Optional[str] = None
    price: Optional[int] = None   # frontend alias
    coins: Optional[int] = None
    price_sum: Optional[int] = None
    stock: Optional[int] = None   # frontend alias
    quantity: Optional[int] = None
    is_active: Optional[bool] = None


class CartAddItem(BaseModel):
    product_id: str
    quantity: int = 1


def _product_out(p: Product):
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "image": p.image,
        "icon": p.icon or "star",
        "category": p.category or "Boshqa",
        "price": p.coins,      # frontend field alias
        "coins": p.coins,
        "price_sum": p.price_sum,
        "stock": p.quantity,   # frontend field alias
        "quantity": p.quantity,
        "is_active": p.is_active,
        "created_at": p.created_at.isoformat(),
    }


def _order_out(order: ShopOrder):
    return {
        "id": str(order.id),
        "user_id": str(order.user_id),
        "status": order.status,
        "created_at": order.created_at.isoformat(),
        "items": [
            {
                "id": str(item.id),
                "product_id": str(item.product_id),
                "product_name": item.product.name if item.product else None,
                "quantity": item.quantity,
                "coin_per_each": item.coin_per_each,
            }
            for item in (order.items or [])
        ],
    }


# ── Products ────────────────────────────────────────────────────────────────

@router.get("/products")
async def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Product).where(Product.is_active == True).offset(skip).limit(limit)
    result = await db.execute(q)
    return [_product_out(p) for p in result.scalars().all()]


@router.post("/products")
async def create_product(
    data: ProductCreate,
    _=Depends(require_permission("coins", "create")),
    db: AsyncSession = Depends(get_db),
):
    p = Product(
        name=data.name,
        description=data.description,
        image=data.image,
        icon=data.icon,
        category=data.category,
        coins=data.effective_coins(),
        price_sum=data.price_sum,
        quantity=data.effective_quantity(),
        is_active=data.is_active,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _product_out(p)


@router.patch("/products/{product_id}")
async def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    _=Depends(require_permission("coins", "update")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Mahsulot topilmadi")
    fields = data.model_dump(exclude_unset=True)
    # Resolve aliases: price→coins, stock→quantity
    if "price" in fields and "coins" not in fields:
        fields["coins"] = fields.pop("price")
    else:
        fields.pop("price", None)
    if "stock" in fields and "quantity" not in fields:
        fields["quantity"] = fields.pop("stock")
    else:
        fields.pop("stock", None)
    for k, v in fields.items():
        if hasattr(p, k):
            setattr(p, k, v)
    await db.commit()
    await db.refresh(p)
    return _product_out(p)


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(
    product_id: uuid.UUID,
    _=Depends(require_permission("coins", "delete")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Mahsulot topilmadi")
    await db.delete(p)
    await db.commit()


# ── Cart / Orders ────────────────────────────────────────────────────────────

async def _load_cart(user_id, db: AsyncSession) -> ShopOrder:
    """Get or create active cart, always with items+product loaded."""
    result = await db.execute(
        select(ShopOrder)
        .options(selectinload(ShopOrder.items).selectinload(CartItem.product))
        .where(ShopOrder.user_id == user_id, ShopOrder.status == "-1")
        .order_by(ShopOrder.created_at.desc())
    )
    order = result.scalar_one_or_none()
    if not order:
        order = ShopOrder(user_id=user_id, status="-1")
        db.add(order)
        await db.commit()
        # Re-query to get fully loaded object (avoids MissingGreenlet on lazy load)
        result2 = await db.execute(
            select(ShopOrder)
            .options(selectinload(ShopOrder.items).selectinload(CartItem.product))
            .where(ShopOrder.id == order.id)
        )
        order = result2.scalar_one()
    return order


@router.get("/cart")
async def get_cart(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order = await _load_cart(current_user.id, db)
    return _order_out(order)


@router.post("/cart/add")
async def add_to_cart(
    data: CartAddItem,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product_id = uuid.UUID(data.product_id)
    prod_result = await db.execute(select(Product).where(Product.id == product_id, Product.is_active == True))
    product = prod_result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Mahsulot topilmadi")

    order = await _load_cart(current_user.id, db)
    item = CartItem(
        order_id=order.id,
        product_id=product_id,
        quantity=data.quantity,
        coin_per_each=product.coins,
    )
    db.add(item)
    await db.commit()
    return _order_out(await _load_cart(current_user.id, db))


@router.delete("/cart/items/{item_id}", status_code=204)
async def remove_cart_item(
    item_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CartItem)
        .join(ShopOrder)
        .where(CartItem.id == item_id, ShopOrder.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Topilmadi")
    await db.delete(item)
    await db.commit()


@router.post("/order")
async def place_order(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Convert active cart to a placed order (status 0)."""
    order = await _load_cart(current_user.id, db)
    if not order.items:
        raise HTTPException(400, "Savat bo'sh")
    order.status = "0"
    await db.commit()
    result = await db.execute(
        select(ShopOrder)
        .options(selectinload(ShopOrder.items).selectinload(CartItem.product))
        .where(ShopOrder.id == order.id)
    )
    return _order_out(result.scalar_one())


@router.get("/orders")
async def order_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ShopOrder)
        .options(selectinload(ShopOrder.items).selectinload(CartItem.product))
        .where(ShopOrder.user_id == current_user.id, ShopOrder.status != "-1")
        .order_by(ShopOrder.created_at.desc())
        .offset(skip).limit(limit)
    )
    return [_order_out(o) for o in result.scalars().all()]
