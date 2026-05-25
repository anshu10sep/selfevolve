"""
Integration tests for the Portfolio Manager Dashboard.
Ensures the dashboard widget updates correctly after a Portfolio Manager rebalance.
"""

import unittest
from agents.skills.portfolio_manager.dashboard_app import DashboardApp

class TestDashboardIntegration(unittest.TestCase):
    def setUp(self):
        """Initialize the dashboard app before each test."""
        self.dashboard = DashboardApp()

    def test_dashboard_updates_after_rebalance(self):
        """
        Test that the dashboard correctly updates and displays the top 20 stocks
        after a portfolio rebalance event.
        """
        # Simulate a list of 25 stocks selected by the portfolio manager
        selected_stocks = [f"TICKER_{i}" for i in range(1, 26)]
        rebalance_timestamp = "2023-11-01 09:30:00"
        
        # Trigger rebalance event
        self.dashboard.on_portfolio_rebalance(selected_stocks, rebalance_timestamp)
        
        # Render the dashboard
        rendered_view = self.dashboard.render_dashboard()
        
        # Assertions for header and timestamp
        self.assertIn(f"Dashboard (Last Rebalance: {rebalance_timestamp})", rendered_view)
        self.assertIn("Top 20 Stocks to Trade:", rendered_view)
        
        # Ensure the first 20 stocks are shown
        for i in range(1, 21):
            self.assertIn(f"{i}. TICKER_{i}", rendered_view)
            
        # Ensure stocks beyond the top 20 are NOT shown
        for i in range(21, 26):
            self.assertNotIn(f"{i}. TICKER_{i}", rendered_view)
        
        # Verify widget state directly
        self.assertEqual(len(self.dashboard.top_stocks_widget.top_stocks), 20)
        self.assertEqual(self.dashboard.top_stocks_widget.top_stocks[0], "TICKER_1")
        self.assertEqual(self.dashboard.top_stocks_widget.top_stocks[-1], "TICKER_20")

    def test_dashboard_empty_state(self):
        """Test the dashboard rendering before any rebalance occurs."""
        rendered_view = self.dashboard.render_dashboard()
        
        self.assertIn("Dashboard (Last Rebalance: Never)", rendered_view)
        self.assertIn("No stocks selected.", rendered_view)

    def test_dashboard_less_than_20_stocks(self):
        """Test the dashboard when fewer than 20 stocks are selected."""
        selected_stocks = ["TSLA", "MSFT", "GOOGL"]
        self.dashboard.on_portfolio_rebalance(selected_stocks, "2023-11-01 10:00:00")
        
        rendered_view = self.dashboard.render_dashboard()
        
        self.assertIn("1. TSLA", rendered_view)
        self.assertIn("2. MSFT", rendered_view)
        self.assertIn("3. GOOGL", rendered_view)
        self.assertNotIn("4.", rendered_view)
        self.assertEqual(len(self.dashboard.top_stocks_widget.top_stocks), 3)

if __name__ == "__main__":
    unittest.main()