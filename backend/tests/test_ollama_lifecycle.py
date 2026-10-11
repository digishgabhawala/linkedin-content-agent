import asyncio

from app.services.ollama_lifecycle import owned_ollama_session


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, models):
        self.models = models
        self.posts = []

    async def get(self, url, timeout):
        return FakeResponse({"models": self.models})

    async def post(self, url, json, timeout):
        self.posts.append((url, json))
        return FakeResponse({})


def test_unloads_only_when_app_loaded_the_configured_model():
    async def scenario():
        client = FakeClient([])
        async with owned_ollama_session(client):
            pass
        assert client.posts == [
            ("http://localhost:11434/api/generate",
             {"model": "qwen3:14b", "keep_alive": 0})
        ]

    asyncio.run(scenario())


def test_preserves_model_that_was_already_loaded():
    async def scenario():
        client = FakeClient([{"name": "qwen3:14b"}])
        async with owned_ollama_session(client):
            pass
        assert client.posts == []

    asyncio.run(scenario())
