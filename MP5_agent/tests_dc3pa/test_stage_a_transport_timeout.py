from __future__ import annotations

from dc3pa_stage_a.run_stage_a_episode import TransportTimeoutEnv


class _Socket:
    def __init__(self):
        self.timeouts = []

    def settimeout(self, timeout):
        self.timeouts.append(timeout)


class _Instance:
    def __init__(self, sock):
        self.client_socket = sock


class _Bridge:
    def __init__(self, sock):
        self._instances = [_Instance(sock)]


class _Env:
    def __init__(self, bridge):
        self._bridge_env = bridge
        self.actions = []

    def step(self, action):
        self.actions.append(action)
        return action


def test_transport_timeout_reaches_nested_malmo_socket():
    sock = _Socket()
    env = _Env(_Bridge(sock))
    wrapped = TransportTimeoutEnv(env, socket_timeout_seconds=17.5)

    assert wrapped.step("mine") == "mine"
    assert env.actions == ["mine"]
    assert sock.timeouts == [17.5]
