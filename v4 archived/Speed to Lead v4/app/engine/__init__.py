"""Engine — the deterministic core (the WAT 'agent' layer, as an always-on service).

Webhook in -> resolve tenant -> load workflow -> call Claude -> execute tools. Routing, SLA
timers, the lead state machine, and all sending are deterministic and live here.
"""
