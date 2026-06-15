import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from models import (
    UserCreate, UserLogin, UserPublic, UserInDB, AuthResponse,
    GenerateRequest, LLD, LLDSummary,
)
from auth import hash_password, verify_password, create_token, get_current_user_id
from drawio_parser import parse_drawio
from cost_estimator import estimate_costs, total_cost
from lld_generator import generate_lld_stream
from exporters import markdown_to_docx

# MongoDB
mongo_url = os.environ["MONGO_URL"]
mongo_client = AsyncIOMotorClient(mongo_url)
db = mongo_client[os.environ["DB_NAME"]]
users_col = db["users"]
llds_col = db["llds"]

app = FastAPI(title="Architecht — Draw.io to LLD")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("architecht")


# ---------- AUTH ----------
@api.post("/auth/register", response_model=AuthResponse)
async def register(payload: UserCreate):
    existing = await users_col.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = UserInDB(
        email=payload.email.lower(),
        name=payload.name,
        password_hash=hash_password(payload.password),
    )
    await users_col.insert_one(user.model_dump())
    token = create_token(user.id, user.email)
    return AuthResponse(token=token, user=UserPublic(id=user.id, email=user.email, name=user.name))


@api.post("/auth/login", response_model=AuthResponse)
async def login(payload: UserLogin):
    doc = await users_col.find_one({"email": payload.email.lower()}, {"_id": 0})
    if not doc or not verify_password(payload.password, doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(doc["id"], doc["email"])
    return AuthResponse(token=token, user=UserPublic(id=doc["id"], email=doc["email"], name=doc["name"]))


@api.get("/auth/me", response_model=UserPublic)
async def me(user_id: str = Depends(get_current_user_id)):
    doc = await users_col.find_one({"id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    return UserPublic(id=doc["id"], email=doc["email"], name=doc["name"])


# ---------- DRAWIO PARSE PREVIEW (no LLM) ----------
@api.post("/drawio/parse")
async def drawio_parse(payload: dict, user_id: str = Depends(get_current_user_id)):
    xml = payload.get("xml", "")
    try:
        parsed = parse_drawio(xml)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    cost_items = estimate_costs(parsed["service_counts"])
    return {
        "pages": parsed["pages"],
        "service_counts": parsed["service_counts"],
        "cost_breakdown": cost_items,
        "estimated_monthly_cost_usd": total_cost(cost_items),
    }


# ---------- LLD GENERATION (streaming) ----------
@api.post("/lld/generate")
async def lld_generate(payload: GenerateRequest, user_id: str = Depends(get_current_user_id)):
    """Streams markdown tokens via SSE, then sends a final event with the saved LLD id."""
    try:
        parsed = parse_drawio(payload.xml)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cost_items = estimate_costs(parsed["service_counts"])
    total = total_cost(cost_items)

    pages_for_layout = [
        {
            "id": p["id"],
            "name": p["name"],
            "nodes": p["nodes"],
            "edges": p["edges"],
        }
        for p in parsed["pages"]
    ]

    async def event_stream():
        # initial meta event
        meta = {
            "type": "meta",
            "pages": [
                {"id": p["id"], "name": p["name"], "node_count": len(p["nodes"]), "edge_count": len(p["edges"])}
                for p in parsed["pages"]
            ],
            "service_counts": parsed["service_counts"],
            "cost_breakdown": cost_items,
            "estimated_monthly_cost_usd": total,
        }
        yield f"data: {json.dumps(meta)}\n\n"

        accumulated: List[str] = []
        try:
            async for chunk in generate_lld_stream(
                title=payload.title,
                pages=parsed["pages"],
                service_counts=parsed["service_counts"],
                cost_breakdown=cost_items,
                total_cost=total,
                xml_excerpt=payload.xml,
            ):
                accumulated.append(chunk)
                yield f"data: {json.dumps({'type': 'delta', 'content': chunk})}\n\n"
        except Exception as e:
            logger.exception("LLD generation failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        markdown = "".join(accumulated)
        lld = LLD(
            user_id=user_id,
            title=payload.title,
            xml=payload.xml,
            markdown=markdown,
            services=[
                {"name": s["name"], "category": s["category"], "count": s["count"], "monthly_cost_usd": s["monthly_cost_usd"]}
                for s in cost_items
            ],
            pages=[
                {"id": p["id"], "name": p["name"], "node_count": len(p["nodes"]), "edge_count": len(p["edges"])}
                for p in parsed["pages"]
            ],
            layout={"pages": pages_for_layout},
            estimated_monthly_cost_usd=total,
        )
        await llds_col.insert_one(lld.model_dump())
        yield f"data: {json.dumps({'type': 'done', 'lld_id': lld.id})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ---------- LLD CRUD ----------
@api.get("/lld", response_model=List[LLDSummary])
async def list_llds(user_id: str = Depends(get_current_user_id)):
    cursor = llds_col.find({"user_id": user_id}, {"_id": 0}).sort("created_at", -1)
    items = await cursor.to_list(200)
    return [
        LLDSummary(
            id=it["id"],
            title=it["title"],
            service_count=len(it.get("services", [])),
            estimated_monthly_cost_usd=it.get("estimated_monthly_cost_usd", 0.0),
            created_at=it["created_at"],
        )
        for it in items
    ]


@api.get("/lld/{lld_id}", response_model=LLD)
async def get_lld(lld_id: str, user_id: str = Depends(get_current_user_id)):
    doc = await llds_col.find_one({"id": lld_id, "user_id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="LLD not found")
    return LLD(**doc)


@api.delete("/lld/{lld_id}")
async def delete_lld(lld_id: str, user_id: str = Depends(get_current_user_id)):
    res = await llds_col.delete_one({"id": lld_id, "user_id": user_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="LLD not found")
    return {"ok": True}


# ---------- EXPORTS ----------
@api.get("/lld/{lld_id}/export/markdown")
async def export_md(lld_id: str, user_id: str = Depends(get_current_user_id)):
    doc = await llds_col.find_one({"id": lld_id, "user_id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="LLD not found")
    safe_name = "".join(c for c in doc["title"] if c.isalnum() or c in ("-", "_")) or "lld"
    return Response(
        content=doc["markdown"],
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.md"'},
    )


@api.get("/lld/{lld_id}/export/docx")
async def export_docx(lld_id: str, user_id: str = Depends(get_current_user_id)):
    doc = await llds_col.find_one({"id": lld_id, "user_id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="LLD not found")
    blob = markdown_to_docx(doc["title"], doc["markdown"])
    safe_name = "".join(c for c in doc["title"] if c.isalnum() or c in ("-", "_")) or "lld"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.docx"'},
    )


# ---------- HEALTH ----------
@api.get("/")
async def root():
    return {"app": "Architecht", "status": "ok"}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    mongo_client.close()
