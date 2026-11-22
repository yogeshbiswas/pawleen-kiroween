"""openai_client with a mocked SDK. No real OpenAI calls."""
import base64
import logging
from types import SimpleNamespace

import openai
import pytest
from pydantic import BaseModel

from app import openai_client
from app.errors import PawleenError, classify_openai_error
from app.pipeline import with_silent_retry
from tests.conftest import test_settings as make_test_settings

PNG = b"\x89PNG-fake-bytes"


class Schema(BaseModel):
    ok: bool


def settings(quality="medium"):
    s = make_test_settings()
    return type(s)(**{**s.__dict__, "image_quality": quality, "image_model": "img-model",
                      "vision_model": "vis-model"})


class FakeImages:
    def __init__(self, result):
        self.result, self.kwargs = result, None

    async def edit(self, **kwargs):
        self.kwargs = kwargs
        return self.result


class FakeResponses:
    def __init__(self, response):
        self.response, self.kwargs = response, None

    async def parse(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def image_result(b64=None):
    b64 = base64.b64encode(PNG).decode() if b64 is None else b64
    return SimpleNamespace(data=[SimpleNamespace(b64_json=b64)])


def test_client_built_with_no_retries(monkeypatch):
    seen = {}
    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: seen.update(kw) or "client")
    s = settings()
    assert openai_client.make_client(s) == "client"
    assert seen == {"api_key": s.openai_api_key, "max_retries": 0}


@pytest.mark.parametrize("quality", ["low", "medium", "high"])
async def test_edit_image_params(quality):
    images = FakeImages(image_result())
    client = SimpleNamespace(images=images)
    out = await openai_client.edit_image(
        client, settings(quality), images=[b"pet"], prompt="p", timeout=7
    )
    assert out == PNG
    kw = images.kwargs
    assert kw["model"] == "img-model"
    assert kw["size"] == "1024x1536"
    assert kw["quality"] == quality
    assert kw["timeout"] == 7
    assert len(kw["image"]) == 1


async def test_edit_image_sends_both_images():
    images = FakeImages(image_result())
    client = SimpleNamespace(images=images)
    await openai_client.edit_image(
        client, settings(), images=[b"pet", b"costume"], prompt="p", timeout=1
    )
    assert [part[1] for part in images.kwargs["image"]] == [b"pet", b"costume"]


@pytest.mark.parametrize(
    "result",
    [SimpleNamespace(data=[]), SimpleNamespace(data=None), image_result(b64=""),
     SimpleNamespace(data=[SimpleNamespace(b64_json=None)]), image_result(b64="!!notbase64")],
)
async def test_missing_image_raises_mapped_error(result):
    client = SimpleNamespace(images=FakeImages(result))
    with pytest.raises(PawleenError) as info:
        await openai_client.edit_image(client, settings(), images=[b"pet"], prompt="p", timeout=1)
    assert info.value.code == "maker_failed"


async def test_vision_json_params():
    parsed = Schema(ok=True)
    responses = FakeResponses(SimpleNamespace(output_parsed=parsed, output=[]))
    client = SimpleNamespace(responses=responses)
    out = await openai_client.vision_json(
        client, settings(), system="sys", user_text="look", image_bytes=b"img",
        mime="image/jpeg", schema=Schema, timeout=5,
    )
    assert out is parsed
    kw = responses.kwargs
    assert kw["model"] == "vis-model"
    assert kw["text_format"] is Schema
    assert kw["timeout"] == 5
    assert kw["store"] is False
    image_part = kw["input"][1]["content"][1]
    assert image_part["type"] == "input_image"
    assert image_part["image_url"].startswith("data:image/jpeg;base64,")


async def _vision_with(response):
    client = SimpleNamespace(responses=FakeResponses(response))
    return await openai_client.vision_json(
        client, settings(), system="s", user_text="t", image_bytes=b"i",
        mime="image/png", schema=Schema, timeout=1,
    )


async def test_none_with_refusal_is_refused():
    refusal = SimpleNamespace(content=[SimpleNamespace(type="refusal")])
    with pytest.raises(PawleenError) as info:
        await _vision_with(SimpleNamespace(output_parsed=None, output=[refusal]))
    assert info.value.code == "refused"


EMPTY_OUTPUT = SimpleNamespace(
    output_parsed=None, output=[SimpleNamespace(content=[SimpleNamespace(type="output_text")])]
)
async def test_none_without_refusal_is_plain_error():
    # Not a PawleenError, so the pipeline retry applies.
    with pytest.raises(RuntimeError, match="empty vision output"):
        await _vision_with(EMPTY_OUTPUT)
    assert classify_openai_error(RuntimeError("empty vision output")) == "temporary_failure"
class SequenceResponses:
    """Returns the scripted responses one by one and counts the calls."""
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), 0
    async def parse(self, **kwargs):
        self.calls += 1
        return self.responses.pop(0)
async def test_gatekeeper_path_retries_once_on_empty_output():
    responses = SequenceResponses(EMPTY_OUTPUT, SimpleNamespace(output_parsed=Schema(ok=True), output=[]))
    client = SimpleNamespace(responses=responses)
    async def call():
        return await openai_client.vision_json(
            client, settings(), system="s", user_text="t", image_bytes=b"i",
            mime="image/png", schema=Schema, timeout=1,
        )
    out = await with_silent_retry(call, 5)
    assert out == Schema(ok=True)
    assert responses.calls == 2
async def test_empty_output_twice_stops_after_two_calls():
    responses = SequenceResponses(EMPTY_OUTPUT, EMPTY_OUTPUT)
    client = SimpleNamespace(responses=responses)
    async def call():
        return await openai_client.vision_json(
            client, settings(), system="s", user_text="t", image_bytes=b"i",
            mime="image/png", schema=Schema, timeout=1,
        )
    with pytest.raises(RuntimeError):
        await with_silent_retry(call, 5)
    assert responses.calls == 2


async def test_no_image_data_in_logs(caplog):
    caplog.set_level(logging.DEBUG)
    b64 = base64.b64encode(PNG).decode()
    client = SimpleNamespace(images=FakeImages(image_result()))
    await openai_client.edit_image(client, settings(), images=[b"pet"], prompt="p", timeout=1)
    await _vision_with(SimpleNamespace(output_parsed=Schema(ok=True), output=[]))
    with pytest.raises(PawleenError):
        await openai_client.edit_image(
            SimpleNamespace(images=FakeImages(SimpleNamespace(data=[]))),
            settings(), images=[b"pet"], prompt="p", timeout=1,
        )
    assert b64 not in caplog.text
    assert base64.b64encode(b"i").decode() not in caplog.text
