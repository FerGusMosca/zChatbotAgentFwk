class PortfolioSecurity:
    def __init__(self, id, portfolio_id, security_id, ticker,symbol, name, cik, added_at, is_active, weight):
        self.id = id
        self.portfolio_id = portfolio_id
        self.security_id = security_id
        self.ticker = ticker
        self.symbol=symbol
        self.name = name
        self.cik = cik
        self.added_at = added_at
        self.is_active = is_active
        self.weight = weight
