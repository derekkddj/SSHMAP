import asyncio
import random

class AsyncRandomQueue:
    def __init__(self, randomize=True):
        self._items = []
        self._event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._unfinished_tasks = 0
        self._all_tasks_done = asyncio.Condition()
        self._randomize = randomize

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
                index = random.randint(0, len(self._items) - 1) if self._randomize else 0
                item = self._items.pop(index)
                if not self._items:
                    self._event.clear()
                return item

    async def remove_where(self, predicate):
        removed = 0
        async with self._lock:
            kept_items = []
            for item in self._items:
                if predicate(item):
                    removed += 1
                else:
                    kept_items.append(item)
            self._items = kept_items
            if not self._items:
                self._event.clear()

        if removed:
            async with self._all_tasks_done:
                self._unfinished_tasks -= removed
                if self._unfinished_tasks == 0:
                    self._all_tasks_done.notify_all()
                elif self._unfinished_tasks < 0:
                    raise ValueError("remove_where() removed too many tasks")

        return removed

    async def drop_by_jumphost(self, jump_host):
        def _matches(item):
            if not isinstance(item, tuple) or len(item) < 3:
                return False
            queued_jump = item[2]
            if queued_jump is None:
                return False
            if hasattr(queued_jump, "get_remote_hostname"):
                try:
                    return queued_jump.get_remote_hostname() == jump_host
                except Exception:
                    return False
            return queued_jump == jump_host

        return await self.remove_where(_matches)

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
