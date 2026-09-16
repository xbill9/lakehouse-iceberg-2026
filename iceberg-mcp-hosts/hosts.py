# -*- coding: utf-8 -*-
"""How each CLI host is driven, and how each is told about an MCP server.

The three differ in a way that matters to the experiment rather than only to the
plumbing, so it is recorded here rather than smoothed over:

  claude   takes --mcp-config per invocation. Nothing global changes, so two
           runs with different servers cannot contaminate each other.
  codex    and
  agy      configure servers in persistent global state (`... mcp add`). To vary
           the server the runner has to mutate that state and put it back, and a
           crash between the two leaves the host configured.

That asymmetry is a finding for the paper: on two of the three hosts, "which
tools does the agent have" is machine state, not a property of the request.
"""
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


class Host(object):
    name = None
    #: Set per cell on axis C. Each host defaults to its own vendor's model, so a
    #: difference between hosts is a difference of host AND model unless this is
    #: pinned -- the confound paper 3 removed by running Strands on Gemini beside
    #: ADK on Gemini. A host that cannot be pointed at the shared model is
    #: reported as such rather than quietly compared.
    model = None

    def with_model(self, model):
        self.model = model
        return self

    def _model_args(self, flag="--model"):
        return [flag, self.model] if self.model else []

    def prepare(self, server):
        """Make `server` the only MCP server this host can see. Return cleanup."""
        raise NotImplementedError

    def ask(self, question, timeout=300):
        raise NotImplementedError

    def version(self):
        raise NotImplementedError


def _run(cmd, timeout, stdin=None):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       input=stdin, cwd=HERE)
    return (p.stdout or "") + (p.stderr or "")


class ClaudeCode(Host):
    name = "claude"

    def prepare(self, server):
        # Written per run and passed with --mcp-config, so nothing global is
        # touched and the previous run's server cannot leak into this one.
        path = os.path.join(HERE, ".mcp-%s.json" % server["key"])
        with open(path, "w") as h:
            json.dump({"mcpServers": {server["key"]: server["spec"]}}, h, indent=2)
        self._cfg = path
        return lambda: os.path.exists(path) and os.remove(path)

    def ask(self, question, timeout=300):
        return _run(["claude", "-p", question,
                     "--mcp-config", self._cfg,
                     "--strict-mcp-config",
                     "--dangerously-skip-permissions"] + self._model_args(), timeout)

    def version(self):
        return _run(["claude", "--version"], 30).strip()


class _GlobalConfigHost(Host):
    """Codex and agy: add the server, run, remove it again."""
    add_cmd = remove_cmd = run_cmd = None

    def prepare(self, server):
        key, spec = server["key"], server["spec"]
        subprocess.run(self.remove_cmd(key), capture_output=True, text=True)
        subprocess.run(self.add_cmd(key, spec), capture_output=True, text=True,
                       check=False)
        return lambda: subprocess.run(self.remove_cmd(key),
                                      capture_output=True, text=True)

    def ask(self, question, timeout=300):
        return _run(self.run_cmd(question), timeout)

    def version(self):
        return _run([self.name, "--version"], 30).strip()


class Codex(_GlobalConfigHost):
    name = "codex"

    def add_cmd(self, key, spec):
        if spec.get("type") == "http":
            return ["codex", "mcp", "add", key, "--url", spec["url"]]
        cmd = ["codex", "mcp", "add", key]
        for k, v in (spec.get("env") or {}).items():
            cmd += ["--env", "%s=%s" % (k, v)]
        return cmd + ["--"] + [spec["command"]] + list(spec.get("args") or [])

    def remove_cmd(self, key):
        return ["codex", "mcp", "remove", key]

    def run_cmd(self, question):
        return (["codex", "exec", "--skip-git-repo-check"]
                + self._model_args("-m") + [question])


class Antigravity(_GlobalConfigHost):
    name = "agy"

    def add_cmd(self, key, spec):
        if spec.get("type") == "http":
            return ["agy", "mcp", "add", "-t", "http", key, spec["url"]]
        cmd = ["agy", "mcp", "add", key]
        for k, v in (spec.get("env") or {}).items():
            cmd += ["--env", "%s=%s" % (k, v)]
        return cmd + [spec["command"]] + list(spec.get("args") or [])

    def remove_cmd(self, key):
        return ["agy", "mcp", "remove", key]

    def run_cmd(self, question):
        return (["agy", "--print", question, "--dangerously-skip-permissions"]
                + self._model_args())


HOSTS = {h.name: h for h in (ClaudeCode(), Codex(), Antigravity())}

#: All three accept --model (claude 2.1.273, codex-cli 0.154.0, agy 1.2.3;
#: codex spells it -m). Whether they all accept the *same* model name is a
#: separate question and is NOT established here -- each defaults to its own
#: vendor's. Axis C pins one and records what actually answered, so a host that
#: rejects it shows up as a refusal rather than as a silent fallback to its
#: default, which would put the confound back without saying so.
MODEL_FLAG = {"claude": "--model", "codex": "-m", "agy": "--model"}
