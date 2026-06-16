import os
import json
import asyncio
import logging
import time
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
    GenerateRequest, LLD, LLDSummary, PublicLLD,
)
from auth import hash_password, verify_password, create_token, get_current_user_id
from drawio_parser import parse_drawio
from cost_estimator import estimate_costs, total_cost
from lld_generator import generate_lld_stream
from exporters import markdown_to_docx
import aws_pricing
import secrets

# MongoDB
mongo_url = os.environ["MONGO_URL"]
allow_invalid_tls = os.environ.get("MONGO_TLS_ALLOW_INVALID_CERTS", "false").lower() in ("1", "true", "yes")
mongo_connect_args = {}
if "mongodb.net" in mongo_url and "tls=" not in mongo_url and "ssl=" not in mongo_url:
    mongo_connect_args["tls"] = True
if allow_invalid_tls:
    mongo_connect_args["tlsAllowInvalidCertificates"] = True
    mongo_connect_args["tlsAllowInvalidHostnames"] = True
mongo_client = AsyncIOMotorClient(mongo_url, **mongo_connect_args)
db = mongo_client[os.environ["DB_NAME"]]
users_col = db["users"]
llds_col = db["llds"]
pricing_cache_col = db["pricing_cache"]

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
    region = payload.get("region", "us-east-1")
    cost_items = await estimate_costs(parsed["service_counts"], region=region, cache_col=pricing_cache_col)
    return {
        "pages": parsed["pages"],
        "service_counts": parsed["service_counts"],
        "cost_breakdown": cost_items,
        "estimated_monthly_cost_usd": total_cost(cost_items),
        "region": region,
    }


# ---------- LLD GENERATION (streaming) ----------
@api.post("/lld/generate")
async def lld_generate(payload: GenerateRequest, user_id: str = Depends(get_current_user_id)):
    """Streams markdown tokens via SSE, then sends a final event with the saved LLD id."""
    try:
        parsed = parse_drawio(payload.xml)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    cost_items = await estimate_costs(parsed["service_counts"], region=payload.region, cache_col=pricing_cache_col)
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
        saved_id: Optional[str] = None
        gen_error: Optional[str] = None
        last_heartbeat = time.time()

        async def persist_now() -> str:
            markdown = "".join(accumulated)
            lld = LLD(
                user_id=user_id,
                title=payload.title,
                xml=payload.xml,
                markdown=markdown,
                services=[
                    {
                        "name": s["name"],
                        "category": s["category"],
                        "count": s["count"],
                        "monthly_cost_usd": s["monthly_cost_usd"],
                        "unit_cost_usd": s.get("unit_cost_usd", 0.0),
                        "assumption": s.get("assumption", ""),
                        "source": s.get("source", "curated"),
                    }
                    for s in cost_items
                ],
                pages=[
                    {"id": p["id"], "name": p["name"], "node_count": len(p["nodes"]), "edge_count": len(p["edges"])}
                    for p in parsed["pages"]
                ],
                layout={"pages": pages_for_layout},
                estimated_monthly_cost_usd=total,
                region=payload.region,
            )
            # shield so client disconnect mid-await still writes to mongo
            await asyncio.shield(llds_col.insert_one(lld.model_dump()))
            return lld.id

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
                # heartbeat every ~8s to keep proxy from idling out the stream
                if time.time() - last_heartbeat > 8:
                    yield ": keepalive\n\n"
                    last_heartbeat = time.time()
        except asyncio.CancelledError:
            # client went away — still try to persist so the work isn't lost
            if accumulated:
                try:
                    saved_id = await persist_now()
                    logger.info("Persisted LLD %s after client disconnect", saved_id)
                except Exception:
                    logger.exception("Persist on cancel failed")
            raise
        except Exception as e:
            logger.exception("LLD generation failed")
            gen_error = str(e)

        if gen_error is not None:
            yield f"data: {json.dumps({'type': 'error', 'message': gen_error})}\n\n"
            return

        if not accumulated:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Empty LLM response'})}\n\n"
            return

        if saved_id is None:
            saved_id = await persist_now()
        yield f"data: {json.dumps({'type': 'done', 'lld_id': saved_id})}\n\n"

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


@api.get("/lld/find-by-title")
async def find_by_title(title: str, user_id: str = Depends(get_current_user_id)):
    """Recovery endpoint: returns the most recent LLD id with this title for the user."""
    doc = await llds_col.find_one(
        {"user_id": user_id, "title": title}, {"_id": 0, "id": 1, "created_at": 1},
        sort=[("created_at", -1)],
    )
    if not doc:
        raise HTTPException(status_code=404, detail="No LLD with that title")
    return {"id": doc["id"], "created_at": doc["created_at"]}



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


# ---------- SHARING ----------
@api.post("/lld/{lld_id}/share")
async def share_lld(lld_id: str, user_id: str = Depends(get_current_user_id)):
    doc = await llds_col.find_one({"id": lld_id, "user_id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="LLD not found")
    token = doc.get("share_token") or secrets.token_urlsafe(18)
    await llds_col.update_one(
        {"id": lld_id, "user_id": user_id},
        {"$set": {"share_token": token, "is_public": True}},
    )
    return {"share_token": token, "is_public": True}


@api.delete("/lld/{lld_id}/share")
async def unshare_lld(lld_id: str, user_id: str = Depends(get_current_user_id)):
    res = await llds_col.update_one(
        {"id": lld_id, "user_id": user_id},
        {"$set": {"is_public": False, "share_token": None}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="LLD not found")
    return {"is_public": False}


@api.get("/public/lld/{token}", response_model=PublicLLD)
async def get_public_lld(token: str):
    """Public, no-auth read-only LLD."""
    doc = await llds_col.find_one(
        {"share_token": token, "is_public": True}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Shared LLD not found or revoked")
    return PublicLLD(
        id=doc["id"],
        title=doc["title"],
        markdown=doc["markdown"],
        services=doc.get("services", []),
        pages=doc.get("pages", []),
        layout=doc.get("layout", {}),
        estimated_monthly_cost_usd=doc.get("estimated_monthly_cost_usd", 0.0),
        region=doc.get("region", "us-east-1"),
        created_at=doc["created_at"],
    )


# ---------- PRICING ----------
@api.get("/pricing")
async def pricing_preview(region: str = "us-east-1"):
    """Show current cached + curated prices for every known service in the region."""
    items = []
    for canonical in aws_pricing.CURATED.keys():
        unit, assumption, source = await aws_pricing.get_price(canonical, region, pricing_cache_col)
        items.append({
            "name": canonical,
            "category": aws_pricing.category_for(canonical),
            "unit_cost_usd": unit,
            "assumption": assumption,
            "source": source,
            "live_capable": canonical in aws_pricing.LIVE_OFFER_CODES,
        })
    return {
        "region": region,
        "items": sorted(items, key=lambda x: x["name"]),
        "supported_regions": sorted(aws_pricing.REGION_MULTIPLIERS.keys()),
    }


@api.post("/pricing/refresh")
async def pricing_refresh(
    region: str = "us-east-1",
    user_id: str = Depends(get_current_user_id),
):
    """Refresh prices for live-capable services in the given region from the
    public AWS Bulk Pricing JSON (no AWS credentials required)."""
    results = await aws_pricing.refresh_all(pricing_cache_col, region=region)
    return {"region": region, "results": results}


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
