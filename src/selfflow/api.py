from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .browser import FlowBrowser, FlowError

app = FastAPI(title="SelfFlow")
browser = FlowBrowser()

# A browser tab is shared; concurrent generations would race on captcha state.
# Serialize access so explicit calls never mutate each other's browser state.
import asyncio
request_lock = asyncio.Lock()


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model: str = "nano-banana-pro"
    aspect: str = "1:1"
    count: int = Field(default=1, ge=1, le=4)
    seed: Optional[int] = None
    project_id: Optional[str] = None
    reference_ids: list[str] = []


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/v1/images/generations")
async def generate_images(request: ImageRequest):
    try:
        async with request_lock:
            images = await browser.generate_images(**request.model_dump())
        return {"data": [{"id": image.media_id, "url": image.url} for image in images]}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except FlowError as error:
        raise HTTPException(status_code=502, detail=str(error))
