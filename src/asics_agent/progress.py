"""Live, plain-language progress from inside the agents ("BWSSB: checking link 3 of 12").

Nodes call `report(key, text)`; the runner streams these with LangGraph's "custom" stream
mode and shows the latest message per parastatal. Outside a streamed run it does nothing.
"""

from langgraph.config import get_stream_writer


def report(key: str, text: str) -> None:
    try:
        writer = get_stream_writer()
    except RuntimeError:  # not running inside a graph (e.g. a direct function call)
        return
    writer({"activity": {"key": key, "text": text}})
