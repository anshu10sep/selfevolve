import asyncio
import logging
from agents.cro_agent import CroAgent
from langchain_core.messages import AIMessage

logging.basicConfig(level=logging.INFO)

class MockLLM:
    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        return AIMessage(content="Simulated CRO text response")

    def with_structured_output(self, schema):
        class MockStructuredLLM:
            async def ainvoke(self, messages):
                return schema(
                    overall_risk_level="CRITICAL",
                    portfolio_drawdown_pct=10.5,
                    max_drawdown_breach=True,
                    halt_recommended=True,
                    reasoning="Drawdown exceeds 8% threshold."
                )
        return MockStructuredLLM()

async def test_csuite():
    print("Testing CRO Agent Risk Assessment...")
    llm = MockLLM()
    cro = CroAgent(llm)
    
    portfolio_state = {
        "total_equity": 90000,
        "available_cash": 90000,
        "open_positions": 0,
        "drawdown_pct": 10.0,  # Simulated 10% drawdown
    }
    
    report = await cro.assess_portfolio_risk(
        portfolio_state=portfolio_state,
        strategy_allocations={},
        recent_trades=[]
    )
    
    print("\n=== CRO RISK REPORT ===")
    print(report)
    print(f"Halt Recommended: {report.halt_recommended}")

if __name__ == "__main__":
    asyncio.run(test_csuite())
