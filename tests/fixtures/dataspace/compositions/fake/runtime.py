class Runtime:
    def __init__(self, *, context, config, path, number, color, session, project, layout, backend, factory):
        self._backend, self._factory = backend, factory
        self._layout = layout
        self._contracts = {"path": path, "number": number, "color": color}

    def definition(self) -> object:
        return self._layout.require("definition")()

    def contract_calls(self, alias: str) -> list:
        return self._contracts[alias].require("calls")()

    def materialize(self, mounts: object) -> object:
        return self._factory.require("materialize")(mounts)

    def backend(self) -> object:
        return self._backend
