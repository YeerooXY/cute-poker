from fastapi.testclient import TestClient

from server import app


client = TestClient(app)


def test_sound_assets_are_served() -> None:
    response = client.get("/sound/poker_sfx_chip_call_250ms_crop.mp3")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")


def test_sound_wav_assets_are_served() -> None:
    response = client.get("/sound/201809__fartheststar__poker_chips5.wav")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
