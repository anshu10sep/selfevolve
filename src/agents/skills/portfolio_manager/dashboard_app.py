"""
Dashboard Application for the Portfolio Manager.
Aggregates widgets and handles events like portfolio rebalancing.
"""

from agents.skills.portfolio_manager.top_stocks_widget import TopStocksWidget

class DashboardApp:
    def __init__(self):
        self.top_stocks_widget = TopStocksWidget()
        self.last_rebalance_time = None

    def on_portfolio_rebalance(self, selected_stocks: list, rebalance_time: str):
        """
        Event handler for portfolio rebalancing.
        Updates the dashboard widgets with the newly selected stocks.
        
        Args:
            selected_stocks (list): List of selected stock tickers.
            rebalance_time (str): Timestamp of the rebalance event.
        """
        self.last_rebalance_time = rebalance_time
        self.top_stocks_widget.update_stocks(selected_stocks)

    def render_dashboard(self) -> str:
        """
        Renders the complete dashboard.
        
        Returns:
            str: The rendered text view of the dashboard.
        """
        header = f"Dashboard (Last Rebalance: {self.last_rebalance_time or 'Never'})"
        separator = "-" * 40
        widget_view = self.top_stocks_widget.render()
        
        return f"{header}\n{separator}\n{widget_view}"