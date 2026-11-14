"""Flow's batchexecute wire format: envelopes, image requests, response readers.

The shape here was derived from the public flowkit/flow-mcp observations of
flow.google.com (2026-09). Google can change it at any time; every assumption
is isolated in this module so a wire change is a one-file fix.
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, Optional

FLOW_ORIGIN = "https://flow.google.com"
BATCH_PATH = "/_/AiSandboxAngularFrontend/data/batchexecute"
MEDIA_HOST = "flow-content.google"

RPC_GENERATE_IMAGE = "ogiZ0b"
RPC_CREATE_PROJECT = "jHPbke"

CAPTCHA_SLOT = "__CAPTCHA__"
CAPTCHA_ACTION = "IMAGE_GENERATION"
SURFACE_ID = 22

MODELS = {
    "nano-banana-pro": "GEM_PIX_2",
    "nano-banana-2": "NARWHAL",
    "nano-banana-2-lite": "HARBOR_SEAL",
}
WIRE_MODELS = set(MODELS.values())

ASPECTS = {
    "1:1": 1,
    "9:16": 2,
    "16:9": 3,
    "3:4": 4,
    "4:3": 5,
}

REF_TYPE_IMAGE = 1
BASE_TYPE_IMAGE = 2


class FlowWireError(RuntimeError):
    pass


@dataclass(frozen=True)
class GeneratedImage:
    media_id: str
    url: str


def _uuid() -> str:
    return str(uuid.uuid4()).upper()


def build_envelope(rpcid: str, inner: Any) -> str:
    return json.dumps(
        [[[rpcid, json.dumps(inner, separators=(",", ":"), ensure_ascii=False), None, "generic"]]],
        separators=(",", ":"),
        ensure_ascii=False,
    )


def parse_envelope(text: str) -> list[tuple[str, Any]]:
    """Return (rpcid, payload) pairs, skipping error slots.

    Length prefixes in batchexecute disagree with character counts when the
    payload contains escapes, so chunks are found by scanning for JSON values.
    """
    if not text:
        return []
    body = text.split("\n", 1)[1] if text.startswith(")]}'") else text
    decoder = json.JSONDecoder()
    out: list[tuple[str, Any]] = []
    index = 0
    while index < len(body):
        start = body.find("[", index)
        if start == -1:
            break
        try:
            chunk, consumed = decoder.raw_decode(body[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        index = start + consumed
        for entry in chunk if isinstance(chunk, list) else []:
            if not isinstance(entry, list) or len(entry) < 3 or entry[0] != "wrb.fr":
                continue
            payload = entry[2]
            if payload is None:
                continue
            out.append((entry[1], json.loads(payload) if isinstance(payload, str) else payload))
    return out


def payload_for(text: str, rpcid: str) -> Any:
    for got, payload in parse_envelope(text):
        if got == rpcid:
            return payload
    raise FlowWireError(f"no {rpcid} payload in batchexecute response")


def resolve_model(name: Optional[str]) -> str:
    key = (name or "nano-banana-pro").strip()
    if key in MODELS:
        return MODELS[key]
    if key in WIRE_MODELS:
        return key
    raise ValueError(f"unknown model {name!r}; use one of {sorted(MODELS)}")


def resolve_aspect(aspect: Any) -> int:
    if isinstance(aspect, bool):
        raise ValueError("aspect ratio must be a label or 1-5")
    if isinstance(aspect, int) and 1 <= aspect <= 5:
        return aspect
    if isinstance(aspect, str) and aspect in ASPECTS:
        return ASPECTS[aspect]
    raise ValueError(f"unknown aspect ratio {aspect!r}; use one of {sorted(ASPECTS)}")


def _context(project_id: Optional[str]) -> list:
    return [
        None, SURFACE_ID, None, None, None, project_id, None, None, None, None,
        [CAPTCHA_SLOT, 1],
    ]


def _image_input(media_id: str, kind: int) -> list:
    return [media_id, None, None, None, kind]


def image_request(
    *,
    prompt: str,
    project_id: str,
    count: int = 1,
    aspect: Any = "1:1",
    model: str = "nano-banana-pro",
    seed: Optional[int] = None,
    references: Iterable[str] = (),
    base_image: Optional[str] = None,
) -> str:
    if not isinstance(count, int) or not 1 <= count <= 4:
        raise ValueError("count must be 1-4")
    ratio = resolve_aspect(aspect)
    wire_model = resolve_model(model)
    base = seed if seed is not None else random.randint(1, 10**9)

    inputs: list = []
    if base_image:
        inputs.append(_image_input(base_image, BASE_TYPE_IMAGE))
    inputs.extend(_image_input(mid, REF_TYPE_IMAGE) for mid in references if mid != base_image)

    items = [
        [
            None, None, inputs or None, base + index * 9973, ratio, wire_model,
            None, _context(project_id), [[[prompt]]], None, None, None,
            _uuid(), _uuid(),
        ]
        for index in range(count)
    ]
    return build_envelope(
        RPC_GENERATE_IMAGE,
        [None, items, 1, _context(project_id), [_uuid()]],
    )


def create_project_request(title: str) -> str:
    clean = " ".join(str(title or "SelfFlow project").split())[:160] or "SelfFlow project"
    return build_envelope(RPC_CREATE_PROJECT, ["projects/*", [None, [clean]], [None, SURFACE_ID]])


def read_created_project(payload: Any) -> str:
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], str):
        raise FlowWireError("project.create returned no project id")
    return payload[0]


def read_images(payload: Any) -> list[GeneratedImage]:
    found: list[GeneratedImage] = []
    seen: set[str] = set()
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            if MEDIA_HOST + "/image/" not in node:
                continue
            media_id = node.split("/image/", 1)[1].split("?", 1)[0]
            if media_id not in seen:
                seen.add(media_id)
                found.append(GeneratedImage(media_id=media_id, url=node))
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            stack.extend(node.values())
    return found


def apply_captcha(freq: str, token: str) -> str:
    return freq.replace(CAPTCHA_SLOT, token)
