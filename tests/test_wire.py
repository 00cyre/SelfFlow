import json
from selfflow import wire


def test_envelope_and_request_shape():
    freq = wire.image_request(prompt="A red boat", project_id="abc", model="nano-banana-pro", aspect="16:9", seed=123, count=2)
    envelope = json.loads(freq)
    rpc = envelope[0][0]
    assert rpc[0] == "ogiZ0b"
    payload = json.loads(rpc[1])
    assert payload[1][0][3] == 123
    assert payload[1][1][3] == 10096
    assert payload[1][0][4] == 3
    assert payload[1][0][5] == "GEM_PIX_2"
    assert payload[1][0][8] == [[["A red boat"]]]
    assert wire.apply_captcha(freq, "token").count("token") == 3


def test_parse_and_extract_image_urls():
    payload = ["something", {"url": "https://flow-content.google/image/media-1?auth=secret"}]
    chunk = json.dumps([["wrb.fr", "ogiZ0b", json.dumps(payload)]])
    text = ")]}'\n" + str(len(chunk)) + "\n" + chunk
    assert wire.payload_for(text, "ogiZ0b") == payload
    assert wire.read_images(payload) == [wire.GeneratedImage(media_id="media-1", url=payload[1]["url"])]


def test_rejects_unknown_model_and_invalid_count():
    try:
        wire.image_request(prompt="x", project_id="abc", model="bad", count=0)
    except ValueError as exc:
        assert "count" in str(exc)
    else:
        raise AssertionError("invalid input accepted")
