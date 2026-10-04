"""Small exceptions used to distinguish client input errors."""


class IRCCommandError(Exception):
    def __init__(self, numeric: str, *params: str) -> None:
        super().__init__(numeric)
        self.numeric = numeric
        self.params = params

