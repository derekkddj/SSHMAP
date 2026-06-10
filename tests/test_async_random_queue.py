import pytest

from modules.helpers.AsyncRandomQueue import AsyncRandomQueue


@pytest.mark.asyncio
async def test_async_random_queue_preserves_order_when_randomization_disabled():
    queue = AsyncRandomQueue(randomize=False)

    await queue.put("first")
    await queue.put("second")
    await queue.put("third")

    assert await queue.get() == "first"
    await queue.task_done()
    assert await queue.get() == "second"
    await queue.task_done()
    assert await queue.get() == "third"
    await queue.task_done()


@pytest.mark.asyncio
async def test_async_random_queue_uses_random_index_when_enabled(mocker):
    queue = AsyncRandomQueue(randomize=True)

    await queue.put("first")
    await queue.put("second")
    await queue.put("third")

    randint = mocker.patch(
        "modules.helpers.AsyncRandomQueue.random.randint", return_value=2
    )

    assert await queue.get() == "third"
    await queue.task_done()
    randint.assert_called_once_with(0, 2)