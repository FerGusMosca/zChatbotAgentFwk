class TagType:

    _RANK="RANK"
    _THRTESHOLD = "THRESHOLD"
    def __init__(self, code: str, name: str, description: str = None):
        self.code = code
        self.name = name
        self.description = description

    def __repr__(self):
        return f"TagType(code='{self.code}', name='{self.name}')"


    def is_rank_report(self):
        return self.code==TagType._RANK


    def is_threshold_report(self):
        return self.code==TagType._THRTESHOLD