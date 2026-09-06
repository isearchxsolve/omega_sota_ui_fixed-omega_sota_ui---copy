"""Gradio UI streaming configuration tests."""

import inspect

import pytest

from omega_agent import Config


def test_chat_stream_is_generator():
    pytest.importorskip("gradio")
    from omega_agent.ui.gradio_app import GradioOmegaApp

    app = GradioOmegaApp(Config(use_mock_llm=True, log_level="ERROR"))
    assert inspect.isgeneratorfunction(app._chat_stream)


def test_send_event_streams_sidebar_only():
    pytest.importorskip("gradio")
    from omega_agent.ui.gradio_app import build_demo

    demo = build_demo(Config(use_mock_llm=True, log_level="ERROR"))
    stream_fns = [
        fn
        for fn in demo.fns.values()
        if getattr(fn.fn, "__name__", "") == "_chat_stream"
    ]
    assert stream_fns
    for fn in stream_fns:
        assert fn.types_generator is True
        assert fn.show_progress == "minimal"
        assert len(fn.outputs) == 6
        assert fn.show_progress_on is not None


def test_pack_stream_uses_plain_values():
    pytest.importorskip("gradio")

    from omega_agent.interaction.session import OmegaChatSession
    from omega_agent.ui.gradio_app import _pack_stream

    session = OmegaChatSession()
    row = _pack_stream(session, "log line", 42, "Running")
    assert len(row) == 6
    assert row[2] == "Running"
    assert row[4] == "log line"
    assert row[5] == 42
    assert isinstance(row[0], list)
