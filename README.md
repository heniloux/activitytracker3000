# ActivityTracker3000 - Desktop Productivity Monitor

ActivityTracker3000 is a cross-platform desktop application built with Python and the CustomTkinter library, designed to help you understand and manage your computer usage patterns for enhanced productivity.

**Key Features:**

*   **Comprehensive Activity Tracking:**
    *   Monitors mouse movements, clicks, and keyboard presses.
    *   Calculates and displays total active and idle time for the day.
    *   Tracks maximum continuous active/idle spells.
    *   Counts total mouse distance, keystrokes, and clicks.
*   **Focus & Break Management:**
    *   Integrated Focus/Break timer (default: 25min focus / 5min break, configurable).
    *   Visual indicators for current timer mode and time remaining.
    *   Logs effectiveness of previous focus sessions.
*   **Flexible Pause Options:**
    *   Manually pause/continue the entire tracking session.
    *   Take timed breaks:
        *   `ADD +5MIN BREAK`: Initiates a 5-minute break or adds 5 minutes to an ongoing 5-minute break.
        *   `PAUSE 30 MIN` / `PAUSE 60 MIN`: Fixed duration breaks.
*   **Effectiveness Insights:**
    *   "Session Effectiveness" percentage and progress bar based on active vs. idle time.
    *   "Focus Session History" displaying effectiveness and details of the last 5 focus periods.
*   **Data & Logging:**
    *   Daily statistics are saved locally in a JSON file (`mouse_activity_log.json`).
    *   Focus session summaries are logged to `focus_session_log.txt`.
    *   Real-time event log within the application GUI.
*   **Customizable:**
    *   Adjust Focus/Break durations.
    *   Set inactivity timeout threshold.
*   **Modern UI:**
    *   Built with CustomTkinter for a sleek, modern dark-themed interface.

This tool aims to provide valuable insights into your work habits, helping you stay focused and manage your breaks effectively.
