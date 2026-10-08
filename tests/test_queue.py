from unittest.mock import ANY, Mock
from uuid import uuid4

from rq.exceptions import DuplicateJobError

from app.core.queue import enqueue_ai_processing


def test_ai_enqueue_uses_atomic_unique_job_id(monkeypatch) -> None:
    queue = Mock()
    monkeypatch.setattr("app.core.queue.get_ai_queue", lambda: queue)
    job_id = uuid4()
    thought_id = uuid4()

    enqueue_ai_processing(job_id, thought_id)

    queue.enqueue.assert_called_once_with(
        ANY,
        str(job_id),
        str(thought_id),
        job_id=str(job_id),
        result_ttl=0,
        unique=True,
    )


def test_duplicate_ai_enqueue_is_already_recovered(monkeypatch) -> None:
    queue = Mock()
    queue.enqueue.side_effect = DuplicateJobError()
    monkeypatch.setattr("app.core.queue.get_ai_queue", lambda: queue)

    enqueue_ai_processing(uuid4(), uuid4())
