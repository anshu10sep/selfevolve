# Owner's Dashboard UI Layout

The Owner's Dashboard is the unified front-end interface. It is designed to be interactive, visually appealing, and highly functional.

## Layout Structure

### 1. Global Navigation Bar (Top)
- **System Health Indicator**: A global green/yellow/red status light representing the Watchdog's holistic assessment.
- **Global Search**: Search for specific agents, PRs, or job IDs.
- **User Profile & Settings**: Authentication and display preferences.

### 2. Main Visualization Canvas (Center)
- **Interactive Architecture Graph**: A live, node-based graph showing Watchdog, Jarvis, Agent Manager, and active agents. 
- **Zoom & Pan**: The owner can zoom out to see the 10,000-foot view, or zoom in to inspect a specific node (e.g., an individual agent).

### 3. Contextual Sidebar (Right)
- When a node on the canvas is clicked, this sidebar populates with detailed metrics and controls.
- **Example Data**: Agent ID, Current Task, Uptime, Success Rate.
- **Example Controls**: `[Execute Job]`, `[Pause Agent]`, `[Terminate Agent]`.

### 4. Live Activity Feed (Bottom)
- A scrolling ticker of critical system events.
- E.g., "Jarvis initiated self-evolution cycle", "Agent-452 raised PR #102 on Repo X".

## Technology Stack (Conceptual)
- **Frontend Framework**: Next.js / React
- **Visualization**: React Flow or D3.js for the interactive node graph.
- **Real-time Data**: WebSockets for streaming state updates from the backend Watchdog.
