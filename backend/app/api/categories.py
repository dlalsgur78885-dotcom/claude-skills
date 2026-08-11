"""채널 그룹(카테고리) 관리 엔드포인트.

⚠ 채널은 그룹을 **이름 문자열**로 참조한다(benchmark_channels.category). 외래키가
아니므로 이름을 바꾸면 채널들이 옛 이름에 매달린 채 어느 그룹에도 안 잡히게 된다.
그래서 이름 변경은 채널까지 같은 트랜잭션에서 함께 갱신한다.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.category import Category
from app.models.channel import BenchmarkChannel
from app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from app.api.auth import get_current_user

router = APIRouter(prefix="/categories", tags=["categories"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    """관리자 전용 게이트. 여기 정의돼 있지만 **이 파일의 라우트는 쓰지 않는다** —
    사용자 관리(users.py)가 임포트해서 쓰므로 남겨둔다.

    카테고리(채널 그룹)는 admin 을 요구하지 않는다. 그룹은 채널을 분류하는 작업용
    도구지 관리자 설정이 아닌데, 실제로 일하는 계정이 전부 worker 라서(로그인 134회의
    junhyeok 포함) 만들 통로 자체가 없었다 — 그래서 카테고리 0개, 그룹 지정 채널 0/86
    상태로 기능이 잠겨 있었다.

    ⚠ 그룹은 소유자 없이 전원이 공유한다. 누구나 만들고 **누구나 지울 수 있다.**
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    return user


@router.get("/", response_model=list[CategoryResponse])
async def list_categories(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Category).order_by(Category.sort_order, Category.name)
    )
    return result.scalars().all()


@router.post("/", response_model=CategoryResponse, status_code=201)
async def create_category(
    data: CategoryCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Category).where(Category.name == data.name)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 존재하는 카테고리입니다")

    category = Category(name=data.name, sort_order=data.sort_order)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Category).where(Category.id == category_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다")

    fields = data.model_dump(exclude_unset=True)
    old_name = category.name
    new_name = (fields.get("name") or "").strip() or None

    if new_name and new_name != old_name:
        # 같은 이름이 둘이 되면 채널이 어느 그룹인지 가릴 수 없다 — 채널이 이름
        # 문자열로만 그룹을 가리키기 때문이다. 미리 막는다.
        dup = await db.scalar(
            select(Category.id).where(
                func.lower(Category.name) == new_name.lower(),
                Category.id != category_id,
            )
        )
        if dup:
            raise HTTPException(status_code=409, detail=f"'{new_name}' 그룹이 이미 있습니다")
        fields["name"] = new_name

    for field, value in fields.items():
        setattr(category, field, value)

    # 이름이 바뀌면 이 그룹을 쓰던 채널들도 같이 옮긴다. 안 하면 채널이 사라진
    # 이름을 계속 가리켜 어느 그룹 필터에도 안 잡힌다.
    if new_name and new_name != old_name:
        await db.execute(
            update(BenchmarkChannel)
            .where(BenchmarkChannel.category == old_name)
            .values(category=new_name)
        )

    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/{category_id}", status_code=204)
async def delete_category(
    category_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Category).where(Category.id == category_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="카테고리를 찾을 수 없습니다")

    await db.delete(category)
    await db.commit()
