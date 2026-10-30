"""Domain exceptions used by the Manager application."""

class ManagerError(Exception):
    def __init__(self, code: str, what: str, do: str):
        self.code, self.what, self.do = code, what, do
        super().__init__(what)

    def render(self) -> str:
        return f"ERROR: {self.code}\nWHAT: {self.what}\nDO: {self.do}"
