# OpenAI findings

Date checked: 2026-11-21. Pinned SDK: `openai==3.57.0` (`requirements.txt`). Signatures below were also read from the installed SDK with `inspect.signature`.

## Pages used

- Image generation guide: https://developers.openai.com/api/docs/guides/image-generation
- Deprecations: https://developers.openai.com/api/docs/deprecations
- Model page, image: https://developers.openai.com/api/docs/models/gpt-image-2.6-sunburst
- Model page, vision: https://developers.openai.com/api/docs/models/gpt-6-luna
- Structured outputs guide: https://developers.openai.com/api/docs/guides/structured-outputs

## Chosen values

| Setting | Value | Why |
|---|---|---|
| `OPENAI_IMAGE_MODEL` | `gpt-image-2.6-sunburst` | The guide recommends Sunburst when editing precision matters (keeping the pet's look). It supports `v1/images/edits` with text and image input. `gpt-image-2.6-flare` is the faster option. |
| `OPENAI_VISION_MODEL` | `gpt-6-luna` | Lists `image_input` and `structured_outputs`, supports the Responses API, and is the cheapest listed model ($0.1 / $0.5 per 1M tokens). It is the deprecations page's replacement for `gpt-4o-mini`. |
| Portrait `size` | `1024x1536` | Listed as the recommended portrait size. |
| Quality | `medium` (default) | See below. |

## How each finding settles the design's open points

- **Model names.** The design's examples are out of date. `gpt-image-1` was retired on Oct 23, 2026 and `gpt-4o-mini` is deprecated (shutdown Jan 14, 2027). `.env.example` uses the verified names above. They stay configuration only and are never hardcoded in code (Req 13.2, 13.3).
- **Size.** Use `1024x1536` for the Costume Maker. It is a documented portrait size and the SDK type accepts it. No design change.
- **Quality.** The API accepts `low`, `medium`, `high`, plus `xhigh`, `max`, `auto` (and `standard` in the SDK type) for the 2.5/2.6 models. The app keeps its own allowed set of `low|medium|high`, default `medium`, so the design's rule (Req 13.12) stands. Extra API values are treated as invalid and fall back to `medium` with a warning. `images.edit` accepts `quality` in the pinned SDK.
- **New, not in the design:** 2.6 models take an optional `complexity` (`low|medium|high`, default `high`). We leave it unset. It can be tuned later for cost.

## SDK call shapes (openai 3.57.0)

Image edit (async client). One or several input images go in `image`; GPT Image models return base64.

```python
from openai import AsyncOpenAI
import base64

client = AsyncOpenAI(api_key=key)
result = await client.images.edit(
    model=settings.image_model,
    image=[("pet.png", pet_bytes, "image/png")],   # add the costume photo as a second item
    prompt=prompt,
    size="1024x1536",
    quality=settings.image_quality,                # low | medium | high
)
png_bytes = base64.b64decode(result.data[0].b64_json)
```

Other `images.edit` parameters in the SDK: `background`, `complexity`, `input_fidelity` (`high|low`), `mask`, `n`, `output_format` (`png|webp|jpeg|gif|svg`), `output_compression`, `response_format`, `safety_identifier`, `stream`, `user`.

Vision with a schema (Responses API `parse`):

```python
response = await client.responses.parse(
    model=settings.vision_model,
    input=[
        {"role": "system", "content": "..."},
        {"role": "user", "content": [
            {"type": "input_text", "text": "..."},
            {"type": "input_image", "image_url": "data:image/png;base64,..."},
        ]},
    ],
    text_format=GatekeeperVerdict,   # pydantic BaseModel
)
verdict = response.output_parsed     # may be None on refusal; handle it
```

`responses.parse` keyword arguments confirmed in the SDK: `model`, `input`, `instructions`, `text_format`, `max_output_tokens`, `store`, `reasoning`, `timeout`, and others. Pass `store=False` so OpenAI does not keep the photos.

The `input_image` item shape and `store=False` come from general Responses API knowledge and the SDK signature, not from a page quoted above. Verify them in the first real call (task for the real agents).
