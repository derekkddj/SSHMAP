import asyncio
import random

class AsyncRandomQueue:
    def __init__(self):
        self._items = []
        self._event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._unfinished_tasks = 0
        self._all_tasks_done = asyncio.Condition()

    async def put(self, item):
        async with self._lock:
            self._items.append(item)
            self._unfinished_tasks += 1
            self._event.set()

    async def get(self):
        while True:
            await self._event.wait()
            async with self._lock:
                if not self._items:
                    self._event.clear()
                    continue
                index = random.randint(0, len(self._items) - 1)
                item = self._items.pop(index)
                if not self._items:
                    self._event.clear()
                return item

    def qsize(self):
        return len(self._items)

    def empty(self):
        return len(self._items) == 0

    async def task_done(self):
        async with self._all_tasks_done:
            self._unfinished_tasks -= 1
            if self._unfinished_tasks == 0:
                self._all_tasks_done.notify_all()
            elif self._unfinished_tasks < 0:
                raise ValueError("task_done() called too many times")

    async def join(self):
        async with self._all_tasks_done:
            while self._unfinished_tasks > 0:
                await self._all_tasks_done.wait()
