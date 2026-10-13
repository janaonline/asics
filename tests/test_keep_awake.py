from unittest import mock

from asics_agent import keep_awake as module


def test_does_nothing_on_other_platforms(monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "linux")
    with mock.patch.object(module.subprocess, "Popen") as popen, module.keep_awake():
        pass
    popen.assert_not_called()


def test_runs_caffeinate_on_mac_and_stops_it_afterwards(monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/caffeinate")
    with mock.patch.object(module.subprocess, "Popen") as popen:
        with module.keep_awake():
            args = popen.call_args.args[0]
            assert args[:3] == ["/usr/bin/caffeinate", "-i", "-w"]
            popen.return_value.terminate.assert_not_called()
        popen.return_value.terminate.assert_called_once()
