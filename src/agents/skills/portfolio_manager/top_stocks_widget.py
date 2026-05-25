"""
Top Stocks Widget for the Portfolio Manager Dashboard.
Displays the top 20 selected stocks to be traded.
"""

class TopStocksWidget:
    def __init__(self):
        self.top_stocks = []

    def update_stocks(self, stocks: list):
        """
        Updates the widget with the top 20 stocks.
        
        Args:
            stocks (list): A list of stock ticker symbols.
        """
        if not isinstance(stocks, list):
            raise ValueError("Stocks must be provided as a list.")
        
        # Keep only the top 20 stocks
        self.top_stocks = stocks[:20]

    def render(self) -> str:
        """
        Renders the top stocks list for the dashboard.
        
        Returns:
            str: The rendered text view of the top 20 stocks.
        """
        if not self.top_stocks:
            return "No stocks selected."
        
        display_lines = ["Top 20 Stocks to Trade:"]
        for i, stock in enumerate(self.top_stocks, 1):
            display_lines.append(f"{i}. {stock}")
            
        return "\n".join(display_lines)