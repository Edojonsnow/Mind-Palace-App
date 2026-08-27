from rq import Worker

from app.core.queue import get_ai_queue, get_redis_connection


def main() -> None:
    connection = get_redis_connection()
    worker = Worker([get_ai_queue()], connection=connection)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
