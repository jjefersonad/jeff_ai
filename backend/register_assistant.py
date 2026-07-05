#!/usr/bin/env python3
"""Register the agent assistant in LangGraph API."""

import asyncio
import aiohttp
import uuid

API_URL = "http://localhost:8000"


async def register_assistant():
    # Generate a valid UUID for assistant_id
    assistant_uuid = str(uuid.uuid4())

    assistant_data = {
        "assistant_id": assistant_uuid,
        "graph_id": "agent",
        "name": "agent",
        "config": {},
        "metadata": {"created_by": "system"}
    }

    print(f"Registering assistant at {API_URL}/assistants...")
    print(f"Assistant ID: {assistant_uuid}")

    async with aiohttp.ClientSession() as session:
        # Try to create assistant
        async with session.post(
            f"{API_URL}/assistants",
            json=assistant_data,
            headers={"Content-Type": "application/json"}
        ) as response:
            result = await response.text()
            print(f"Status: {response.status}")
            print(f"Response: {result}")

        # Check if assistant was created
        async with session.post(
            f"{API_URL}/assistants/search",
            json={},
            headers={"Content-Type": "application/json"}
        ) as response:
            result = await response.text()
            print(f"\nAssistants: {result}")


if __name__ == "__main__":
    asyncio.run(register_assistant())