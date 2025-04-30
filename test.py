import asyncio

async def worker(name):
    try:
        while True:
            print(f"{name} working...")
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        print(f"{name} was cancelled.")
        raise

async def main():
    tasks = [
        asyncio.create_task(worker("Task A")),
        asyncio.create_task(worker("Task B"))
    ]
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        print("Ctrl+C received! Cancelling tasks...")
        # Cancel all tasks
        for task in tasks:
            task.cancel()
        # Wait for all tasks to finish and handle cancellation
        await asyncio.gather(*tasks, return_exceptions=True)
        print("All tasks cancelled. Exiting cleanly.")

if __name__ == "__main__":
    try:
        asyncio.run(main())  # Run the asyncio event loop
    except KeyboardInterrupt:
        print("Program terminated by user.")
