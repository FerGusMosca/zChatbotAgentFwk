class TagSource:
    def __init__(self, code: str, name: str, description: str = None):
        self.code = code
        self.name = name
        self.description = description

    def __repr__(self):
        return f"TagSource(code='{self.code}', name='{self.name}')"