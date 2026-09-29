
from typing import TypedDict


class State(TypedDict):
    question: str
    embedding_res: list
    keyword_res: list
    answer: str
    info: str
    file_nos: list
    citation_status: str
    retry_count: int
    is_danger: bool


def test_check_danger():
    assert False


def test_retrieve_by_knowledge_graph():
    assert False
