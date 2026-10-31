from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import Course, CourseInvite, CourseMember, User
from .schemas import CourseIn, InviteIn
from .security import current_user, new_id, new_secret, token_digest, utcnow

router = APIRouter(prefix="/api", tags=["courses"])


def request_origin(request: Request) -> str:
    raw = request.headers.get("origin", "")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="A valid browser origin is required")
    if parsed.path or parsed.query or parsed.fragment:
        raise HTTPException(status_code=400, detail="Invalid browser origin")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=400, detail="Secure origin required")
    return f"{parsed.scheme}://{parsed.netloc}"


async def membership(db: AsyncSession, course_id: str, user_id: str) -> CourseMember:
    row = await db.scalar(
        select(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == user_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return row


@router.get("/courses")
async def list_courses(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)) -> list[dict[str, object]]:
    rows = await db.execute(
        select(Course, CourseMember.role)
        .join(CourseMember, CourseMember.course_id == Course.id)
        .where(CourseMember.user_id == user.id)
        .order_by(Course.created_at.desc())
    )
    return [
        {"id": course.id, "name": course.name, "role": role, "created_at": course.created_at.isoformat()}
        for course, role in rows.all()
    ]


@router.post("/courses", status_code=201)
async def create_course(
    payload: CourseIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, str]:
    course = Course(id=new_id(), name=payload.name, owner_id=user.id)
    db.add(course)
    db.add(CourseMember(id=new_id(), course_id=course.id, user_id=user.id, role="owner"))
    await db.commit()
    return {"id": course.id, "name": course.name, "role": "owner"}


@router.get("/courses/{course_id}")
async def get_course(
    course_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, object]:
    member = await membership(db, course_id, user.id)
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"id": course.id, "name": course.name, "role": member.role, "created_at": course.created_at.isoformat()}


@router.post("/courses/{course_id}/invites", status_code=201)
async def create_invite(
    course_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, str]:
    origin = request_origin(request)
    member = await membership(db, course_id, user.id)
    if member.role != "owner":
        raise HTTPException(status_code=403, detail="Only the course owner can create invite links")
    raw = new_secret()
    invite = CourseInvite(
        id=new_id(),
        course_id=course_id,
        created_by=user.id,
        token_hash=token_digest(raw),
        expires_at=utcnow() + timedelta(days=7),
    )
    db.add(invite)
    await db.commit()
    return {"invite_url": f"{origin}/#invite={raw}", "expires_at": invite.expires_at.isoformat()}


@router.post("/invites/accept")
async def accept_invite(
    payload: InviteIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, str]:
    invite = await db.scalar(
        select(CourseInvite)
        .where(CourseInvite.token_hash == token_digest(payload.token))
        .with_for_update()
    )
    if invite is None or invite.expires_at <= utcnow():
        raise HTTPException(status_code=400, detail="Invite link is invalid or expired")
    if invite.accepted_at is not None and invite.accepted_by != user.id:
        raise HTTPException(status_code=400, detail="Invite link has already been used")
    already_member = await db.scalar(
        select(CourseMember.id).where(CourseMember.course_id == invite.course_id, CourseMember.user_id == user.id)
    )
    if already_member is None:
        db.add(CourseMember(id=new_id(), course_id=invite.course_id, user_id=user.id, role="member"))
    if invite.accepted_at is None:
        invite.accepted_by = user.id
        invite.accepted_at = utcnow()
    course = await db.get(Course, invite.course_id)
    if course is None:
        raise HTTPException(status_code=400, detail="Invite link is invalid or expired")
    await db.commit()
    return {"course_id": course.id, "course_name": course.name, "role": "member"}
